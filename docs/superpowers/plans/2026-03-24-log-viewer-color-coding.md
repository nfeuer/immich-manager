# Log Viewer Color Coding & Filtering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-level color coding and multi-select filtering to the server manager log viewer.

**Architecture:** Backend classifies each log line into one of five levels (`error`, `warn`, `info`, `debug`, `untagged`) after stripping ANSI escape codes; snapshot and stream endpoints return `{level, text}` dicts/JSON instead of plain strings. Frontend renders each line in its level color and provides multi-select filter buttons.

**Tech Stack:** Python 3.12 + regex, React 18 + Tailwind CSS, Vitest + Testing Library, pytest

**Spec:** `docs/superpowers/specs/2026-03-24-log-viewer-color-coding-design.md`

---

## File Map

| File | Change |
|------|--------|
| `server-manager/src/logs.py` | Add `_strip_ansi()`, `classify_line()`; modify `get_log_snapshot()` return type, `stream_log_lines()` yield type; add lines cap |
| `server-manager/tests/test_logs.py` | **New** — unit tests for `classify_line` and `_strip_ansi` |
| `server-manager/frontend/src/components/LogViewer.jsx` | Add filter state + bar + count; update state type, SSE handler, error path, line rendering |
| `server-manager/frontend/src/test/LogViewer.test.jsx` | Update mock shape; add filter behavior tests |

---

## Task 1: Backend — add `_strip_ansi` and `classify_line` (TDD)

**Files:**
- Create: `server-manager/tests/test_logs.py`
- Modify: `server-manager/src/logs.py`

- [ ] **Step 1: Write failing tests**

Create `server-manager/tests/test_logs.py`:

```python
import pytest
from src.logs import classify_line, _strip_ansi


# --- _strip_ansi ---

def test_strip_ansi_removes_color_codes():
    assert _strip_ansi('\x1b[31mERROR\x1b[0m') == 'ERROR'

def test_strip_ansi_removes_cursor_movement():
    assert _strip_ansi('\x1b[2Jhello') == 'hello'

def test_strip_ansi_passthrough_clean_line():
    line = 'Mar 23 20:35:27 host svc[123]: INFO started'
    assert _strip_ansi(line) == line


# --- classify_line: journalctl short format ---

def test_classify_journalctl_error():
    assert classify_line('Mar 23 20:35:27 host svc[123]: ERROR database connection failed') == 'error'

def test_classify_journalctl_warn():
    assert classify_line('Mar 23 20:35:27 host svc[123]: WARNING disk usage high') == 'warn'

def test_classify_journalctl_info():
    assert classify_line('Mar 23 20:35:27 host svc[123]: INFO service started') == 'info'

def test_classify_journalctl_debug():
    assert classify_line('Mar 23 20:35:27 host svc[123]: DEBUG processing request') == 'debug'

def test_classify_journalctl_untagged():
    assert classify_line('Mar 23 20:35:27 host svc[123]: something happened') == 'untagged'


# --- classify_line: Docker structured format ---

def test_classify_docker_error():
    assert classify_line('time="2024-03-23T20:35:27Z" level=error msg="failed"') == 'error'

def test_classify_docker_warn():
    assert classify_line('time="2024-03-23T20:35:27Z" level=warn msg="slow query"') == 'warn'

def test_classify_docker_info():
    assert classify_line('time="2024-03-23T20:35:27Z" level=info msg="started"') == 'info'

def test_classify_docker_debug():
    assert classify_line('time="2024-03-23T20:35:27Z" level=debug msg="trace"') == 'debug'

def test_classify_docker_untagged():
    assert classify_line('time="2024-03-23T20:35:27Z" msg="container started"') == 'untagged'


# --- classify_line: Python logging format ---

def test_classify_python_error():
    assert classify_line('2024-03-23 20:35:27,123 - myapp.db - ERROR - connection refused') == 'error'

def test_classify_python_warn():
    assert classify_line('2024-03-23 20:35:27,123 - myapp - WARNING - deprecated call') == 'warn'

def test_classify_python_info():
    assert classify_line('2024-03-23 20:35:27,123 - myapp - INFO - request completed') == 'info'

def test_classify_python_debug():
    assert classify_line('2024-03-23 20:35:27,123 - myapp - DEBUG - entering function') == 'debug'

def test_classify_python_untagged():
    assert classify_line('2024-03-23 20:35:27,123 - myapp - NOTICE - something') == 'untagged'


# --- Priority and edge cases ---

def test_classify_error_beats_warn():
    # Both error and warn keywords present; error wins (higher priority)
    assert classify_line('WARN: ERROR count exceeded threshold') == 'error'

def test_classify_case_insensitive():
    assert classify_line('error: something bad') == 'error'
    assert classify_line('Error: something bad') == 'error'

def test_classify_ansi_stripped_before_classification():
    # ANSI codes around ERROR keyword must not prevent classification
    assert classify_line('\x1b[31mERROR\x1b[0m: something failed') == 'error'

def test_classify_third_party_output_is_untagged():
    line = '/opt/photo-curator/venv/lib/python3.12/site-packages/insightface/utils/face_align.py:23: FutureWarning'
    assert classify_line(line) == 'untagged'

def test_classify_warn_keyword_variant():
    assert classify_line('WARN something') == 'warn'
    assert classify_line('WARNING something') == 'warn'
```

- [ ] **Step 2: Run tests — expect all FAIL**

```bash
cd /home/feuer/Documents/Projects/immich-manager/server-manager
python -m pytest tests/test_logs.py -v 2>&1 | head -40
```

Expected: `ImportError` or `AttributeError` — `classify_line` and `_strip_ansi` do not exist yet.

- [ ] **Step 3: Implement `_strip_ansi` and `classify_line` in `logs.py`**

Add the following imports at the top of `server-manager/src/logs.py` (after the existing imports):

```python
import json
import re
```

Add these constants and functions directly after the `_JOURNALCTL_UNITS` dict (before `_container_name`):

```python
_ANSI_RE = re.compile(r'\x1b\[[0-9;]*[A-Za-z]')

_LEVEL_PATTERNS = [
    ('error', re.compile(r'\bERROR\b|level=error', re.IGNORECASE)),
    ('warn',  re.compile(r'\bWARN(?:ING)?\b|level=warn(?:ing)?', re.IGNORECASE)),
    ('info',  re.compile(r'\bINFO\b|level=info', re.IGNORECASE)),
    ('debug', re.compile(r'\bDEBUG\b|level=debug', re.IGNORECASE)),
]


def _strip_ansi(line: str) -> str:
    """Remove ANSI/CSI escape sequences from a log line."""
    return _ANSI_RE.sub('', line)


def classify_line(line: str) -> str:
    """Classify a log line into a level: error, warn, info, debug, or untagged.

    Strips ANSI codes before matching. Patterns evaluated in priority order;
    first match wins.
    """
    clean = _strip_ansi(line)
    for level, pattern in _LEVEL_PATTERNS:
        if pattern.search(clean):
            return level
    return 'untagged'
```

- [ ] **Step 4: Run tests — expect all PASS**

```bash
cd /home/feuer/Documents/Projects/immich-manager/server-manager
python -m pytest tests/test_logs.py -v
```

Expected: all 23 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/feuer/Documents/Projects/immich-manager
git add server-manager/src/logs.py server-manager/tests/test_logs.py
git commit -m "feat(logs): add ANSI stripping and log level classification"
```

---

## Task 2: Backend — update `get_log_snapshot` and `stream_log_lines`

**Files:**
- Modify: `server-manager/src/logs.py`

- [ ] **Step 1: Replace `get_log_snapshot` body**

Current signature at line 35: `def get_log_snapshot(service: str, lines: int = 200) -> List[str]:`

Replace the function with:

```python
def get_log_snapshot(service: str, lines: int = 200) -> List[dict]:
    """Return the last `lines` log lines for the given service as classified dicts."""
    lines = min(lines, 2000)
    if service in _DOCKER_SERVICES:
        raw = _docker_snapshot(service, lines)
    elif service in _JOURNALCTL_UNITS:
        raw = _journal_snapshot(_JOURNALCTL_UNITS[service], lines)
    elif service == "system":
        raw = _journal_snapshot(None, lines)
    else:
        logger.warning("Unknown log service requested: %s", service)
        return []
    result = []
    for line in raw:
        text = _strip_ansi(line)
        result.append({"level": classify_line(text), "text": text})
    return result
```

- [ ] **Step 2: Replace `stream_log_lines` body**

Current signature at line 47: `def stream_log_lines(service: str) -> Generator[str, None, None]:`

Replace the function with:

```python
def stream_log_lines(service: str) -> Generator[str, None, None]:
    """Yield classified log lines as JSON strings for the given service."""
    if service in _DOCKER_SERVICES:
        raw = _docker_stream(service)
    elif service in _JOURNALCTL_UNITS:
        raw = _journal_stream(_JOURNALCTL_UNITS[service])
    elif service == "system":
        raw = _journal_stream(None)
    else:
        logger.warning("Unknown log service stream requested: %s", service)
        return
    for line in raw:
        text = _strip_ansi(line)
        yield json.dumps({"level": classify_line(text), "text": text})
```

- [ ] **Step 3: Run full backend test suite**

```bash
cd /home/feuer/Documents/Projects/immich-manager/server-manager
python -m pytest tests/ -v
```

Expected: all tests PASS (no regressions).

- [ ] **Step 4: Commit**

```bash
cd /home/feuer/Documents/Projects/immich-manager
git add server-manager/src/logs.py
git commit -m "feat(logs): return classified {level, text} dicts from snapshot and stream"
```

---

## Task 3: Frontend — update `LogViewer.jsx` state and rendering

**Files:**
- Modify: `server-manager/frontend/src/components/LogViewer.jsx`

- [ ] **Step 1: Replace the full file content**

Replace `server-manager/frontend/src/components/LogViewer.jsx` with:

```jsx
import { useState, useEffect, useRef, useCallback } from 'react'
import { DocumentTextIcon } from '@heroicons/react/24/outline'

const SERVICES = [
  'immich_server',
  'immich_machine_learning',
  'immich_postgres',
  'immich_redis',
  'server_manager',
  'photo_curator',
  'system',
]

const TAB_LABELS = {
  immich_server: 'immich_server',
  immich_machine_learning: 'ml',
  immich_postgres: 'postgres',
  immich_redis: 'redis',
  server_manager: 'server_manager',
  photo_curator: 'photo_curator',
  system: 'system',
}

const LEVELS = ['error', 'warn', 'info', 'debug', 'untagged']

const LEVEL_LABELS = {
  error: 'Error',
  warn: 'Warn',
  info: 'Info',
  debug: 'Debug',
  untagged: 'Untagged',
}

const LEVEL_COLORS = {
  error: 'text-red-400',
  warn: 'text-yellow-400',
  info: 'text-gray-300',
  debug: 'text-gray-500',
  untagged: 'text-orange-400',
}

const FILTER_ACTIVE_CLASSES = {
  error: 'text-red-400 border-red-400 bg-red-400/10',
  warn: 'text-yellow-400 border-yellow-400 bg-yellow-400/10',
  info: 'text-gray-300 border-gray-300 bg-gray-300/10',
  debug: 'text-gray-500 border-gray-500 bg-gray-500/10',
  untagged: 'text-orange-400 border-orange-400 bg-orange-400/10',
}

export default function LogViewer() {
  const [selectedService, setSelectedService] = useState(SERVICES[0])
  const [isLive, setIsLive] = useState(false)
  const [logLines, setLogLines] = useState([])
  const [loading, setLoading] = useState(false)
  const [activeFilters, setActiveFilters] = useState(new Set())
  const outputRef = useRef(null)
  const eventSourceRef = useRef(null)

  const stopStream = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }
  }, [])

  const loadSnapshot = useCallback(async (service) => {
    setLoading(true)
    try {
      const r = await fetch(`/api/logs/${encodeURIComponent(service)}`)
      if (!r.ok) throw new Error(r.status)
      const data = await r.json()
      setLogLines(data.lines ?? [])
    } catch (e) {
      setLogLines([{ level: 'error', text: `Error loading logs: ${e.message}` }])
    } finally {
      setLoading(false)
    }
  }, [])

  const startStream = useCallback((service) => {
    stopStream()
    setLogLines([])
    const es = new EventSource(`/api/logs/${encodeURIComponent(service)}/stream`)
    es.onmessage = (e) => {
      let entry
      try {
        entry = JSON.parse(e.data)
      } catch {
        entry = { level: 'untagged', text: e.data }
      }
      setLogLines((prev) => [...prev, entry])
    }
    es.onerror = () => {
      stopStream()
      setIsLive(false)
    }
    eventSourceRef.current = es
  }, [stopStream])

  useEffect(() => {
    stopStream()
    if (isLive) {
      startStream(selectedService)
    } else {
      loadSnapshot(selectedService)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedService])

  useEffect(() => {
    if (isLive) {
      startStream(selectedService)
    } else {
      stopStream()
      loadSnapshot(selectedService)
    }
    return stopStream
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLive])

  // Auto-scroll on every new line (regardless of filter)
  useEffect(() => {
    if (isLive && outputRef.current) {
      outputRef.current.scrollTop = outputRef.current.scrollHeight
    }
  }, [logLines, isLive])

  const visibleLines = activeFilters.size === 0
    ? logLines
    : logLines.filter((l) => activeFilters.has(l.level))

  const toggleFilter = (level) => {
    setActiveFilters((prev) => {
      const next = new Set(prev)
      if (next.has(level)) next.delete(level)
      else next.add(level)
      return next
    })
  }

  return (
    <div className="bg-immich-surface border border-immich-border rounded-2xl p-5 mb-6">
      <h2 className="text-xs font-semibold uppercase tracking-wider text-immich-muted mb-4 flex items-center gap-1.5">
        <DocumentTextIcon className="w-3.5 h-3.5" /> Log Viewer
      </h2>

      {/* Service tab bar */}
      <div className="flex flex-wrap gap-1 mb-3 border-b border-immich-border pb-3">
        {SERVICES.map((svc) => (
          <button
            key={svc}
            aria-label={svc}
            onClick={() => setSelectedService(svc)}
            className={`px-3 py-1.5 text-xs font-mono rounded-lg transition-colors duration-150 border-b-2 ${
              selectedService === svc
                ? 'text-immich-primary border-immich-primary bg-immich-primary/10'
                : 'text-immich-muted border-transparent hover:text-immich-text hover:bg-immich-border/50'
            }`}
          >
            {TAB_LABELS[svc]}
          </button>
        ))}
      </div>

      {/* Controls */}
      <div className="flex items-center gap-4 mb-3">
        <button
          onClick={() => !isLive && loadSnapshot(selectedService)}
          disabled={isLive}
          className="px-3 py-1.5 bg-immich-primary hover:bg-blue-600 disabled:opacity-40 text-white rounded-lg text-xs font-medium transition-colors duration-150"
        >
          Refresh
        </button>
        <label className="flex items-center gap-2 cursor-pointer select-none text-xs text-immich-muted">
          <input
            type="checkbox"
            checked={isLive}
            onChange={(e) => setIsLive(e.target.checked)}
            className="cursor-pointer"
          />
          <span className="flex items-center gap-1.5">
            {isLive && (
              <span className="inline-block w-2 h-2 rounded-full bg-green-500 animate-pulse" />
            )}
            Live
          </span>
        </label>
      </div>

      {/* Level filter bar */}
      <div className="flex flex-wrap items-center gap-1.5 mb-2">
        <button
          onClick={() => setActiveFilters(new Set())}
          className={`px-2.5 py-1 text-xs font-medium rounded-md border transition-colors duration-150 ${
            activeFilters.size === 0
              ? 'text-immich-primary border-immich-primary bg-immich-primary/10'
              : 'text-immich-muted border-immich-border hover:text-immich-text hover:bg-immich-border/50'
          }`}
        >
          All
        </button>
        {LEVELS.map((level) => (
          <button
            key={level}
            onClick={() => toggleFilter(level)}
            className={`px-2.5 py-1 text-xs font-medium rounded-md border transition-colors duration-150 ${
              activeFilters.has(level)
                ? FILTER_ACTIVE_CLASSES[level]
                : 'text-immich-muted border-immich-border hover:text-immich-text hover:bg-immich-border/50'
            }`}
          >
            {LEVEL_LABELS[level]}
          </button>
        ))}
        <span className="ml-auto text-xs text-immich-muted">
          {activeFilters.size > 0
            ? `${visibleLines.length} of ${logLines.length} lines`
            : logLines.length > 0 ? `${logLines.length} lines` : null}
        </span>
      </div>

      {/* Output */}
      <div
        ref={outputRef}
        className="bg-[#080810] rounded-xl p-3 text-xs font-mono h-96 overflow-y-auto"
      >
        {loading ? (
          <span className="text-gray-300">Loading…</span>
        ) : visibleLines.length > 0 ? (
          visibleLines.map((line, i) => (
            <div
              key={i}
              className={`whitespace-pre-wrap break-all leading-relaxed ${LEVEL_COLORS[line.level] ?? 'text-gray-300'}`}
            >
              {line.text}
            </div>
          ))
        ) : logLines.length === 0 ? (
          <span className="text-gray-300">Select a service to load logs.</span>
        ) : (
          <span className="text-gray-500">No lines match the active filter.</span>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Run frontend tests**

```bash
cd /home/feuer/Documents/Projects/immich-manager/server-manager/frontend
npm test 2>&1 | tail -30
```

Expected: existing tests (`renders all 7 service tabs`, `preserves selected tab`) may fail because the mock still returns plain strings. That is expected — Task 4 will fix the tests.

- [ ] **Step 3: Commit**

```bash
cd /home/feuer/Documents/Projects/immich-manager
git add server-manager/frontend/src/components/LogViewer.jsx
git commit -m "feat(log-viewer): add level color coding, filter bar, and structured line rendering"
```

---

## Task 4: Frontend — update `LogViewer.test.jsx`

**Files:**
- Modify: `server-manager/frontend/src/test/LogViewer.test.jsx`

- [ ] **Step 1: Replace the full test file**

```jsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import LogViewer from '../components/LogViewer.jsx'

beforeEach(() => {
  global.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({
      lines: [
        { level: 'info', text: 'log line 1' },
        { level: 'warn', text: 'log line 2' },
        { level: 'error', text: 'log line 3' },
      ],
    }),
  })
  global.EventSource = vi.fn().mockImplementation(() => ({
    onmessage: null,
    onerror: null,
    close: vi.fn(),
  }))
})

describe('LogViewer', () => {
  it('renders all 7 service tabs', () => {
    render(React.createElement(LogViewer))
    expect(screen.getByRole('button', { name: /immich_server/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /system/ })).toBeInTheDocument()
  })

  it('preserves selected tab when re-rendered by parent', () => {
    const { rerender } = render(React.createElement(LogViewer))
    fireEvent.click(screen.getByRole('button', { name: /server_manager/ }))
    rerender(React.createElement(LogViewer))
    const tab = screen.getByRole('button', { name: /server_manager/ })
    expect(tab.className).toMatch(/border-immich-primary/)
  })

  it('renders log lines with text content', async () => {
    render(React.createElement(LogViewer))
    await waitFor(() => {
      expect(screen.getByText('log line 1')).toBeInTheDocument()
      expect(screen.getByText('log line 2')).toBeInTheDocument()
      expect(screen.getByText('log line 3')).toBeInTheDocument()
    })
  })

  it('renders All filter button as active by default', () => {
    render(React.createElement(LogViewer))
    const allBtn = screen.getByRole('button', { name: /^All$/ })
    expect(allBtn.className).toMatch(/border-immich-primary/)
  })

  it('clicking a level filter hides non-matching lines', async () => {
    render(React.createElement(LogViewer))
    await waitFor(() => screen.getByText('log line 1'))

    fireEvent.click(screen.getByRole('button', { name: /^Error$/ }))

    expect(screen.queryByText('log line 1')).not.toBeInTheDocument() // info
    expect(screen.queryByText('log line 2')).not.toBeInTheDocument() // warn
    expect(screen.getByText('log line 3')).toBeInTheDocument()       // error
  })

  it('clicking All resets filter and shows all lines', async () => {
    render(React.createElement(LogViewer))
    await waitFor(() => screen.getByText('log line 1'))

    fireEvent.click(screen.getByRole('button', { name: /^Error$/ }))
    fireEvent.click(screen.getByRole('button', { name: /^All$/ }))

    expect(screen.getByText('log line 1')).toBeInTheDocument()
    expect(screen.getByText('log line 2')).toBeInTheDocument()
    expect(screen.getByText('log line 3')).toBeInTheDocument()
  })

  it('shows filtered line count when a filter is active', async () => {
    render(React.createElement(LogViewer))
    await waitFor(() => screen.getByText('log line 1'))

    fireEvent.click(screen.getByRole('button', { name: /^Error$/ }))

    expect(screen.getByText(/1 of 3 lines/)).toBeInTheDocument()
  })

  it('shows total line count with no filter active', async () => {
    render(React.createElement(LogViewer))
    await waitFor(() => screen.getByText(/3 lines/))
    expect(screen.getByText('3 lines')).toBeInTheDocument()
  })

  it('shows empty filter message when no lines match', async () => {
    render(React.createElement(LogViewer))
    await waitFor(() => screen.getByText('log line 1'))

    fireEvent.click(screen.getByRole('button', { name: /^Debug$/ }))

    expect(screen.getByText(/No lines match the active filter/)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run frontend tests — expect all PASS**

```bash
cd /home/feuer/Documents/Projects/immich-manager/server-manager/frontend
npm test 2>&1 | tail -30
```

Expected: all tests PASS.

- [ ] **Step 3: Commit**

```bash
cd /home/feuer/Documents/Projects/immich-manager
git add server-manager/frontend/src/test/LogViewer.test.jsx
git commit -m "test(log-viewer): update mock shape and add filter behavior tests"
```

---

## Task 5: Rebuild frontend dist

- [ ] **Step 1: Build**

```bash
cd /home/feuer/Documents/Projects/immich-manager/server-manager/frontend
npm run build
```

Expected: build succeeds with no errors.

- [ ] **Step 2: Commit the new dist**

```bash
cd /home/feuer/Documents/Projects/immich-manager
git add server-manager/frontend/dist/
git commit -m "build: rebuild frontend with log viewer color coding and filtering"
```
