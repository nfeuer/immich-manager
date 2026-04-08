import { useState, useRef, useEffect } from 'react'
import { ArrowPathIcon, WrenchScrewdriverIcon } from '@heroicons/react/24/outline'
import ConfirmDialog from './ConfirmDialog.jsx'
import { useInlineConfirm } from '../hooks/useInlineConfirm.js'

const SERVICES = [
  'immich_server',
  'immich_machine_learning',
  'immich_postgres',
  'immich_redis',
  'server_manager',
  'photo_curator',
]

function ButtonContent({ state, armed }) {
  if (state === 'loading') return <ArrowPathIcon className="w-3.5 h-3.5 animate-spin" />
  if (state === 'ok') return <span>✓</span>
  if (state === 'error') return <span>✗</span>
  if (armed) return <span className="text-[10px] leading-tight">Confirm?</span>
  return <span>Restart</span>
}

export default function ServiceControls() {
  const [states, setStates] = useState({}) // { [service]: 'idle' | 'loading' | 'ok' | 'error' }
  const [restartAllOpen, setRestartAllOpen] = useState(false)
  const [bannerMessage, setBannerMessage] = useState(null) // { type: 'ok' | 'error', text: string }
  const { isArmed, trigger } = useInlineConfirm()
  const timeoutRef = useRef(null)
  const bannerTimeoutRef = useRef(null)

  useEffect(() => {
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current)
      if (bannerTimeoutRef.current) clearTimeout(bannerTimeoutRef.current)
    }
  }, [])

  function showBanner(type, text) {
    setBannerMessage({ type, text })
    if (bannerTimeoutRef.current) clearTimeout(bannerTimeoutRef.current)
    bannerTimeoutRef.current = setTimeout(() => setBannerMessage(null), 4000)
  }

  async function performRestart(service) {
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

  function handleRestartClick(service) {
    trigger(service, () => { performRestart(service) })
  }

  async function restartAll() {
    setRestartAllOpen(false)
    try {
      const r = await fetch('/api/services/restart-all', { method: 'POST' })
      const data = await r.json()
      if (r.ok) {
        showBanner('ok', 'All services restarted.')
      } else {
        showBanner('error', `Failed: ${data.detail ?? 'unknown error'}`)
      }
    } catch {
      showBanner('error', 'Failed to restart all services.')
    }
  }

  return (
    <div className="bg-immich-surface border border-immich-border rounded-2xl p-5 mb-6">
      <h2 className="text-sm font-semibold text-immich-text mb-4 flex items-center gap-1.5">
        <WrenchScrewdriverIcon className="w-3.5 h-3.5" /> Service Controls
      </h2>
      <div className="space-y-2">
        {SERVICES.map((svc) => {
          const armed = isArmed(svc)
          const state = states[svc] ?? 'idle'
          return (
            <div key={svc} className="flex items-center justify-between py-1.5 border-b border-immich-border last:border-0">
              <span className="text-sm font-mono text-immich-text">{svc}</span>
              <button
                type="button"
                onClick={() => { handleRestartClick(svc) }}
                disabled={state === 'loading'}
                aria-label={armed ? `Confirm restart ${svc}` : `Restart ${svc}`}
                className={`px-3 py-1.5 disabled:opacity-50 text-white rounded-lg text-xs font-medium transition-colors duration-150 min-w-[80px] flex items-center justify-center focus:outline-none focus-visible:ring-2 ${
                  armed
                    ? 'bg-immich-warning text-immich-bg focus-visible:ring-immich-warning'
                    : 'bg-immich-primary hover:bg-immich-primary-hover focus-visible:ring-immich-primary'
                }`}
              >
                <ButtonContent state={state} armed={armed} />
              </button>
            </div>
          )
        })}
      </div>
      {bannerMessage && (
        <div
          role="status"
          className={`mt-3 px-3 py-2 rounded-lg text-sm border ${
            bannerMessage.type === 'ok'
              ? 'bg-immich-success-muted border-immich-success-border text-immich-success'
              : 'bg-immich-error-muted border-immich-error-border text-immich-error'
          }`}
        >
          {bannerMessage.text}
        </div>
      )}
      <div className="mt-4 flex justify-end">
        <button
          type="button"
          onClick={() => { setRestartAllOpen(true) }}
          className="px-4 py-2 bg-immich-warning hover:bg-immich-warning/90 text-immich-bg rounded-lg text-sm font-medium transition-colors duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-warning"
        >
          Restart All Immich Services
        </button>
      </div>
      <ConfirmDialog
        open={restartAllOpen}
        title="Restart all Immich services?"
        description="This will briefly interrupt Immich for all users. Proceed?"
        confirmLabel="Restart All"
        confirmVariant="warning"
        onConfirm={restartAll}
        onCancel={() => setRestartAllOpen(false)}
      />
    </div>
  )
}
