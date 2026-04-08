import { useState, useRef, useEffect } from 'react'
import { ArrowPathIcon, WrenchScrewdriverIcon } from '@heroicons/react/24/outline'

const SERVICES = [
  'immich_server',
  'immich_machine_learning',
  'immich_postgres',
  'immich_redis',
  'server_manager',
  'photo_curator',
]

function ButtonContent({ state }) {
  if (state === 'loading') return <ArrowPathIcon className="w-3.5 h-3.5 animate-spin" />
  if (state === 'ok') return <span>✓</span>
  if (state === 'error') return <span>✗</span>
  return <span>Restart</span>
}

export default function ServiceControls() {
  const [states, setStates] = useState({}) // { [service]: 'idle' | 'loading' | 'ok' | 'error' }
  const timeoutRef = useRef(null)

  useEffect(() => {
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current)
    }
  }, [])

  async function restartService(service) {
    if (!window.confirm(`Restart ${service}?`)) return
    setStates((s) => ({ ...s, [service]: 'loading' }))
    try {
      const r = await fetch(`/api/services/${encodeURIComponent(service)}/restart`, { method: 'POST' })
      setStates((s) => ({ ...s, [service]: r.ok ? 'ok' : 'error' }))
    } catch {
      setStates((s) => ({ ...s, [service]: 'error' }))
    }
    if (timeoutRef.current) clearTimeout(timeoutRef.current)
    timeoutRef.current = setTimeout(() => setStates((s) => ({ ...s, [service]: 'idle' })), 3000)
  }

  async function restartAll() {
    if (!window.confirm('Restart ALL Immich services? This will briefly interrupt Immich.')) return
    try {
      const r = await fetch('/api/services/restart-all', { method: 'POST' })
      const data = await r.json()
      window.alert(r.ok ? 'All services restarted.' : `Failed: ${data.detail ?? 'unknown error'}`)
    } catch {
      window.alert('Failed to restart all services.')
    }
  }

  return (
    <div className="bg-immich-surface border border-immich-border rounded-2xl p-5 mb-6">
      <h2 className="text-xs font-semibold uppercase tracking-wider text-immich-muted mb-4 flex items-center gap-1.5">
        <WrenchScrewdriverIcon className="w-3.5 h-3.5" /> Service Controls
      </h2>
      <div className="space-y-2">
        {SERVICES.map((svc) => (
          <div key={svc} className="flex items-center justify-between py-1.5 border-b border-immich-border last:border-0">
            <span className="text-sm font-mono text-immich-text">{svc}</span>
            <button
              type="button"
              onClick={() => { restartService(svc) }}
              disabled={(states[svc] ?? 'idle') === 'loading'}
              aria-label={`Restart ${svc}`}
              className="px-3 py-1.5 bg-immich-primary hover:bg-blue-600 disabled:opacity-50 text-white rounded-lg text-xs font-medium transition-colors duration-150 min-w-[64px] flex items-center justify-center focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-primary"
            >
              <ButtonContent state={states[svc] ?? 'idle'} />
            </button>
          </div>
        ))}
      </div>
      <div className="mt-4 flex justify-end">
        <button
          type="button"
          onClick={() => { restartAll() }}
          className="px-4 py-2 bg-amber-500 hover:bg-amber-600 text-white rounded-lg text-sm font-medium transition-colors duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-400"
        >
          Restart All Immich Services
        </button>
      </div>
    </div>
  )
}
