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

export default function LogViewer() {
  const [selectedService, setSelectedService] = useState(SERVICES[0])
  const [isLive, setIsLive] = useState(false)
  const [logLines, setLogLines] = useState([])
  const [loading, setLoading] = useState(false)
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
      setLogLines([`Error loading logs: ${e.message}`])
    } finally {
      setLoading(false)
    }
  }, [])

  const startStream = useCallback((service) => {
    stopStream()
    setLogLines([])
    const es = new EventSource(`/api/logs/${encodeURIComponent(service)}/stream`)
    es.onmessage = (e) => {
      setLogLines((prev) => [...prev, e.data])
    }
    es.onerror = () => {
      stopStream()
      setIsLive(false)
    }
    eventSourceRef.current = es
  }, [stopStream])

  // When service changes: stop any stream, load snapshot (or restart stream if live)
  useEffect(() => {
    stopStream()
    if (isLive) {
      startStream(selectedService)
    } else {
      loadSnapshot(selectedService)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedService])

  // When live toggled on/off
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

  // Auto-scroll when live
  useEffect(() => {
    if (isLive && outputRef.current) {
      outputRef.current.scrollTop = outputRef.current.scrollHeight
    }
  }, [logLines, isLive])

  return (
    <div className="bg-immich-surface border border-immich-border rounded-2xl p-5 mb-6">
      <h2 className="text-xs font-semibold uppercase tracking-wider text-immich-muted mb-4 flex items-center gap-1.5">
        <DocumentTextIcon className="w-3.5 h-3.5" /> Log Viewer
      </h2>

      {/* Tab bar */}
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

      {/* Output */}
      <pre
        ref={outputRef}
        className="bg-[#080810] text-gray-300 rounded-xl p-3 text-xs font-mono h-96 overflow-y-auto whitespace-pre-wrap break-all leading-relaxed"
      >
        {loading ? 'Loading…' : logLines.length ? logLines.join('\n') : 'Select a service to load logs.'}
      </pre>
    </div>
  )
}
