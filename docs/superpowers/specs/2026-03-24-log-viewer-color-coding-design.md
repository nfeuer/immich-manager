# Log Viewer Color Coding & Filtering — Design Spec

**Date:** 2026-03-24
**Status:** Approved

## Problem

The log viewer renders all lines as plain text, making it hard to spot errors. Users must manually scan through hundreds of lines to find `ERROR` or `WARN` entries. Third-party package output (untagged lines with no level indicator) blends in with structured application logs.

## Goals

- Color code log lines by level so errors are immediately visible
- Highlight untagged lines (third-party/raw print output) as anomalies
- Add multi-select level filter buttons to reduce noise
- Structure log line data in the backend for future integrations (alerting, search, stats)

## Architecture

### Backend — `logs.py`

**ANSI stripping:** Before classification, each raw line is stripped of ANSI escape codes (e.g. `\x1b[31m...\x1b[0m`). Docker containers (Immich, PostgreSQL, Redis) emit colored output; without stripping, level keywords embedded in escape sequences will not match. A regex `re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', line)` is applied to the raw text before `classify_line` is called. Using `[A-Za-z]` as the terminator (rather than just `m`) covers all CSI escape sequences including cursor movement and erase codes, not just SGR color codes. The `text` field in the output dict contains the ANSI-stripped line.

**`classify_line(line: str) -> str`** returns one of five levels. Patterns are evaluated in priority order — first match wins:

| Priority | Level | Criteria |
|----------|-------|----------|
| 1 | `error` | Line contains `ERROR`, `level=error`, `[ERROR]`, etc. (case-insensitive) |
| 2 | `warn` | Line contains `WARN`, `WARNING`, `level=warn`, `[WARN]`, etc. |
| 3 | `info` | Line contains `INFO`, `level=info`, `[INFO]`, etc. |
| 4 | `debug` | Line contains `DEBUG`, `level=debug`, `[DEBUG]`, etc. |
| 5 | `untagged` | None of the above match |

A line matching both `warn` and `error` patterns (e.g. `WARN: ERROR count: 1`) resolves to `error` because `error` is evaluated first. The function is a pure regex operation and does not throw; no try/except is needed.

Patterns must cover the three common formats present in this stack:
- **journalctl short** (`Mar 23 20:35:27 host svc[pid]: MESSAGE`) — level keyword appears in the MESSAGE portion
- **Docker/structured** (`time="..." level=error msg="..."`) — `level=<value>` key-value pair
- **Python logging** (`2024-03-23 20:35:27,123 - module - ERROR - message`) — level word between dashes

**Multiline log entries:** Each physical line is classified independently. Continuation lines (e.g. stack trace frames, SQL dumps from PostgreSQL) will typically match `untagged` since they lack a level keyword. This is acceptable and expected — the orange highlight on continuation lines in fact aids readability by visually grouping them as anomalies. No multiline joining is performed.

**`lines` parameter cap:** `get_log_snapshot` accepts a `lines: int` parameter. The backend enforces a maximum of 2000; values above this are clamped to 2000 before passing to Docker/journalctl.

**Changed signatures:**

- `get_log_snapshot(service, lines) -> List[dict]`
  Each dict: `{"level": "info", "text": "<ansi-stripped line>"}`

- `stream_log_lines(service) -> Generator[str, None, None]`
  Yields JSON strings: `'{"level": "error", "text": "<ansi-stripped line>"}'`
  The same ANSI stripping and `classify_line` call applied in the snapshot path must also be applied to each line in the streaming path before yielding, so live and snapshot views are consistent.

### API layer — `main.py`

No structural changes. The snapshot endpoint already returns `{"lines": [...]}` — the list now contains dicts instead of strings. The SSE stream endpoint already sends `data: <value>\n\n` — the value is now a JSON-encoded dict instead of a plain string.

### Frontend — `LogViewer.jsx`

**State:** `logLines` holds `{level: string, text: string}[]` instead of `string[]`.

**Data handling:**
- Snapshot: `data.lines` is already the right shape, no parsing needed
- SSE: `JSON.parse(e.data)` before appending to `logLines`; if parsing fails, append `{level: "untagged", text: e.data}` (graceful degradation, no crash)
- Snapshot fetch error: `setLogLines([{level: "error", text: "Error loading logs: <message>"}])` — error path yields a dict, not a bare string

**Filter bar:** Multi-select toggle buttons above the log output.
Levels: `All | Error | Warn | Info | Debug | Untagged`

- `All` is a dedicated reset button, not a toggleable level. Clicking it clears all individual selections and shows every line.
- Individual level buttons (`Error`, `Warn`, `Info`, `Debug`, `Untagged`) are independently toggleable. Active buttons are visually highlighted.
- When all individual buttons are deselected, the view silently shows all lines and the `All` button returns to its active/highlighted visual state.
- Filtered line count shown beneath the filter bar:
  - When a filter is active: `"12 of 200 lines"`
  - When no filter is active (All): `"200 lines"`

**Line rendering:** Replace the `<pre>` text join with a scrollable `<div>` containing one `<div>` per visible line.

Color map (against `#080810` dark background):

| Level | Color class | Rationale |
|-------|------------|-----------|
| `error` | `text-red-400` | High visibility, clearly dangerous |
| `warn` | `text-yellow-400` | Caution, attention needed |
| `info` | `text-gray-300` | Default, no emphasis |
| `debug` | `text-gray-500` | Dimmed, low priority |
| `untagged` | `text-orange-400` | Stands out as anomaly, distinct from warn |

No background highlights — text color only to keep the log readable.

**Auto-scroll in live mode:** Auto-scroll continues to trigger on every `logLines` state change (i.e. every new incoming line), regardless of whether that line passes the active filter. This keeps the viewport tracking the live tail even when most lines are filtered out.

## Data Flow

```
raw line (with possible ANSI codes)
    → strip ANSI → classify_line()
        → get_log_snapshot() / stream_log_lines()
            → main.py snapshot endpoint / SSE stream
                → LogViewer.jsx state (List[{level, text}])
                    → filter buttons → visible lines
                        → colored <div> per line
```

## Error Handling

- SSE lines that fail JSON parsing: append `{level: "untagged", text: e.data}` (no crash)
- Snapshot fetch failure: `setLogLines([{level: "error", text: "Error loading logs: <message>"}])`
- `lines` parameter above 2000: clamped to 2000 by the backend

## Testing

- Unit tests for `classify_line` in `server-manager/tests/test_logs.py` (new file), covering:
  - All five levels × all three log formats = 15 minimum cases
  - Priority tie-break: a line matching both `error` and `warn` resolves to `error`
  - ANSI-prefixed level keyword still classifies correctly after stripping
- Frontend: `LogViewer.test.jsx` updated to mock the new `{level, text}` response shape and test filter toggle behavior. The mock fetch response must use:
  ```js
  { lines: [{ level: "info", text: "log line 1" }, { level: "warn", text: "log line 2" }] }
  ```
