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

Add a `classify_line(line: str) -> str` function that returns one of five levels:

| Level | Criteria |
|-------|----------|
| `error` | Line contains `ERROR`, `error`, `level=error`, `[ERROR]`, etc. (case-insensitive regex) |
| `warn` | Line contains `WARN`, `WARNING`, `level=warn`, `[WARN]`, etc. |
| `info` | Line contains `INFO`, `level=info`, `[INFO]`, etc. |
| `debug` | Line contains `DEBUG`, `level=debug`, `[DEBUG]`, etc. |
| `untagged` | None of the above match |

Patterns must cover the three common formats present in this stack:
- **journalctl short** (`Mar 23 20:35:27 host svc[pid]: MESSAGE`) — level keyword appears in the MESSAGE portion
- **Docker/structured** (`time="..." level=error msg="..."`) — `level=<value>` key-value pair
- **Python logging** (`2024-03-23 20:35:27,123 - module - ERROR - message`) — level word between dashes

**Changed signatures:**

- `get_log_snapshot(service, lines) -> List[dict]`
  Each dict: `{"level": "info", "text": "<raw line>"}`

- `stream_log_lines(service) -> Generator[str, None, None]`
  Yields JSON strings: `'{"level": "error", "text": "<raw line>"}'`

### API layer — `main.py`

No structural changes. The snapshot endpoint already returns `{"lines": [...]}` — the list now contains dicts instead of strings. The SSE stream endpoint already sends `data: <value>\n\n` — the value is now a JSON-encoded dict instead of a plain string.

### Frontend — `LogViewer.jsx`

**State:** `logLines` holds `{level: string, text: string}[]` instead of `string[]`.

**Data handling:**
- Snapshot: `data.lines` is already the right shape, no parsing needed
- SSE: `JSON.parse(e.data)` before appending to `logLines`

**Filter bar:** Multi-select toggle buttons above the log output.
Levels: `All | Error | Warn | Info | Debug | Untagged`
- `All` selected by default (shows everything)
- Clicking any level button toggles it; active levels are highlighted
- When no individual level is toggled, fall back to showing all lines
- Filtered count shown: e.g. `"12 of 200 lines"`

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

## Data Flow

```
logs.py classify_line()
    → get_log_snapshot() / stream_log_lines()
        → main.py snapshot endpoint / SSE stream
            → LogViewer.jsx state (List[{level, text}])
                → filter buttons → visible lines
                    → colored <div> per line
```

## Error Handling

- Lines that fail JSON parsing in the SSE handler are displayed as `untagged` with the raw event data as text (graceful degradation, no crash)
- The `classify_line` regex is non-throwing; an exception falls back to `"untagged"`

## Testing

- Unit tests for `classify_line` covering all five levels across all three log formats
- Frontend: existing `LogViewer.test.jsx` updated to mock the new `{level, text}` response shape
