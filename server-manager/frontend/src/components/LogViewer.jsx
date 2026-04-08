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

const MAX_LINES = 2000

const LEVEL_LABELS = {
  error: 'Error',
  warn: 'Warn',
  info: 'Info',
  debug: 'Debug',
  untagged: 'Untagged',
}

const LEVEL_COLORS = {
  error: 'text-immich-error',
  warn: 'text-immich-warning',
  info: 'text-immich-log-info',
  debug: 'text-immich-log-debug',
  untagged: 'text-immich-log-untagged',
}

const FILTER_ACTIVE_CLASSES = {
  error: 'text-immich-error border-immich-error bg-immich-error/10',
  warn: 'text-immich-warning border-immich-warning bg-immich-warning/10',
  info: 'text-immich-log-info border-immich-log-info bg-immich-log-info/10',
  debug: 'text-immich-log-debug border-immich-log-debug bg-immich-log-debug/10',
  untagged: 'text-immich-log-untagged border-immich-log-untagged bg-immich-log-untagged/10',
}

export default function LogViewer() {
  const [selectedService, setSelectedService] = useState(SERVICES[0])
  const [isLive, setIsLive] = useState(false)
  const [logLines, setLogLines] = useState([])
  const [loading, setLoading] = useState(false)
  const [activeFilters, setActiveFilters] = useState(new Set())
  const outputRef = useRef(null)
  const eventSourceRef = useRef(null)
  const pendingLinesRef = useRef([])
  const flushRafRef = useRef(null)
  const scrollRafRef = useRef(null)

  const stopStream = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }
    if (flushRafRef.current != null) {
      cancelAnimationFrame(flushRafRef.current)
      flushRafRef.current = null
    }
    pendingLinesRef.current = []
  }, [])

  const loadSnapshot = useCallback(async (service) => {
    setLoading(true)
    try {
      const r = await fetch(`/api/logs/${encodeURIComponent(service)}`)
      if (!r.ok) throw new Error(r.status)
      const data = await r.json()
      const lines = data.lines ?? []
      setLogLines(lines.length > MAX_LINES ? lines.slice(-MAX_LINES) : lines)
    } catch (e) {
      setLogLines([{ level: 'error', text: `Error loading logs: ${e.message}` }])
    } finally {
      setLoading(false)
    }
  }, [])

  const flushPendingLines = useCallback(() => {
    flushRafRef.current = null
    if (pendingLinesRef.current.length === 0) return
    const batch = pendingLinesRef.current
    pendingLinesRef.current = []
    setLogLines((prev) => {
      const next = [...prev, ...batch]
      return next.length > MAX_LINES ? next.slice(-MAX_LINES) : next
    })
  }, [])

  const startStream = useCallback((service) => {
    stopStream()
    setLogLines([])
    pendingLinesRef.current = []
    const es = new EventSource(`/api/logs/${encodeURIComponent(service)}/stream`)
    es.onmessage = (e) => {
      let entry
      try {
        entry = JSON.parse(e.data)
      } catch {
        entry = { level: 'untagged', text: e.data }
      }
      pendingLinesRef.current.push(entry)
      if (flushRafRef.current == null) {
        flushRafRef.current = requestAnimationFrame(flushPendingLines)
      }
    }
    es.onerror = () => {
      stopStream()
      setIsLive(false)
    }
    eventSourceRef.current = es
  }, [stopStream, flushPendingLines])

  useEffect(() => {
    stopStream()
    setActiveFilters(new Set())
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

  // Auto-scroll on new lines, batched via rAF to avoid layout thrashing
  useEffect(() => {
    if (isLive && outputRef.current) {
      if (scrollRafRef.current != null) cancelAnimationFrame(scrollRafRef.current)
      scrollRafRef.current = requestAnimationFrame(() => {
        scrollRafRef.current = null
        if (outputRef.current) {
          outputRef.current.scrollTop = outputRef.current.scrollHeight
        }
      })
    }
  }, [logLines, isLive])

  const visibleLines = logLines
    .map((line, idx) => ({ line, idx }))
    .filter(({ line }) => activeFilters.size === 0 || activeFilters.has(line.level))

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
            type="button"
            key={svc}
            onClick={() => setSelectedService(svc)}
            className={`px-3 py-1.5 text-xs font-mono rounded-lg transition-colors duration-150 border-b-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-primary ${
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
          type="button"
          onClick={() => !isLive && loadSnapshot(selectedService)}
          disabled={isLive}
          className="px-3 py-1.5 bg-immich-primary hover:bg-immich-primary-hover disabled:opacity-40 text-white rounded-lg text-xs font-medium transition-colors duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-primary"
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
              <span className="inline-block w-2 h-2 rounded-full bg-immich-success animate-pulse" />
            )}
            Live
          </span>
        </label>
        {logLines.length >= MAX_LINES && (
          <span className="text-xs text-immich-muted">Showing last {MAX_LINES.toLocaleString()} lines</span>
        )}
      </div>

      {/* Level filter bar */}
      <div className="flex flex-wrap items-center gap-1.5 mb-2">
        <button
          type="button"
          onClick={() => setActiveFilters(new Set())}
          className={`px-2.5 py-1 text-xs font-medium rounded-md border transition-colors duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-primary ${
            activeFilters.size === 0
              ? 'text-immich-primary border-immich-primary bg-immich-primary/10'
              : 'text-immich-muted border-immich-border hover:text-immich-text hover:bg-immich-border/50'
          }`}
        >
          All
        </button>
        {LEVELS.map((level) => (
          <button
            type="button"
            key={level}
            onClick={() => toggleFilter(level)}
            className={`px-2.5 py-1 text-xs font-medium rounded-md border transition-colors duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-primary ${
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
        role="log"
        aria-label="Service log output"
        className="bg-immich-terminal rounded-xl p-3 text-xs font-mono h-64 sm:h-80 md:h-96 lg:h-[32rem] overflow-y-auto"
      >
        {loading ? (
          <span className="text-immich-log-info">Loading…</span>
        ) : visibleLines.length > 0 ? (
          visibleLines.map(({ line, idx }) => (
            <div
              key={idx}
              className={`whitespace-pre-wrap break-all leading-relaxed ${LEVEL_COLORS[line.level] ?? 'text-immich-log-info'}`}
            >
              {line.text}
            </div>
          ))
        ) : logLines.length === 0 ? (
          <span className="text-immich-log-info">Select a service to load logs.</span>
        ) : (
          <span className="text-immich-log-debug">No lines match the active filter.</span>
        )}
      </div>
    </div>
  )
}
