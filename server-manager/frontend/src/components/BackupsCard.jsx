import { useState, useRef, useEffect } from 'react'
import { ArchiveBoxIcon, CheckCircleIcon, XCircleIcon } from '@heroicons/react/24/outline'
import { useBackups } from '../hooks/useDashboard.js'
import { useInlineConfirm } from '../hooks/useInlineConfirm.js'
import StatusBadge from './StatusBadge.jsx'

function BackupStatusBadge({ status }) {
  const ok = status === 'success'
  return (
    <StatusBadge variant={ok ? 'success' : 'error'}>
      {ok ? <CheckCircleIcon className="w-3 h-3" /> : <XCircleIcon className="w-3 h-3" />}
      {status}
    </StatusBadge>
  )
}

export default function BackupsCard() {
  const { data, isLoading } = useBackups()
  const history = (data?.history ?? []).slice(0, 3)
  const { isArmed, trigger } = useInlineConfirm()
  const [message, setMessage] = useState(null) // { type, text }
  const messageTimeoutRef = useRef(null)

  useEffect(() => {
    return () => { if (messageTimeoutRef.current) clearTimeout(messageTimeoutRef.current) }
  }, [])

  function showMessage(type, text) {
    setMessage({ type, text })
    if (messageTimeoutRef.current) clearTimeout(messageTimeoutRef.current)
    messageTimeoutRef.current = setTimeout(() => setMessage(null), 4000)
  }

  async function doBackup() {
    try {
      const r = await fetch('/api/backup/now', { method: 'POST' })
      if (r.ok) {
        showMessage('ok', 'Backup started!')
      } else {
        showMessage('error', 'Failed to start backup.')
      }
    } catch {
      showMessage('error', 'Failed to start backup.')
    }
  }

  const armed = isArmed('backup')

  return (
    <div className="bg-immich-surface border border-immich-border rounded-2xl p-5 flex flex-col">
      <h2 className="text-sm font-semibold text-immich-text mb-4">Backups</h2>
      {isLoading ? (
        <p className="text-immich-muted text-sm">Loading…</p>
      ) : history.length === 0 ? (
        <p className="text-immich-muted text-sm mb-4">No backups yet</p>
      ) : (
        <div className="space-y-2 mb-4 flex-1">
          {history.map((b) => (
            <div key={b.timestamp} className="flex items-center justify-between">
              <span className="text-xs text-immich-muted">
                {new Date(b.timestamp).toLocaleDateString()}
              </span>
              <BackupStatusBadge status={b.status} />
            </div>
          ))}
        </div>
      )}
      <button
        type="button"
        onClick={() => { trigger('backup', doBackup) }}
        aria-label={armed ? 'Confirm start backup' : 'Start backup now'}
        className={`mt-auto w-full px-4 py-2 text-white rounded-lg text-sm font-medium transition-colors duration-150 flex items-center justify-center gap-2 focus:outline-none focus-visible:ring-2 ${
          armed
            ? 'bg-immich-warning text-immich-bg focus-visible:ring-immich-warning'
            : 'bg-immich-primary hover:bg-immich-primary-hover focus-visible:ring-immich-primary'
        }`}
      >
        <ArchiveBoxIcon className="w-4 h-4" />
        {armed ? 'Click again to confirm' : 'Backup Now'}
      </button>
      {message && (
        <p
          role="status"
          className={`mt-2 text-xs text-center ${
            message.type === 'ok' ? 'text-immich-success' : 'text-immich-error'
          }`}
        >
          {message.text}
        </p>
      )}
    </div>
  )
}
