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
