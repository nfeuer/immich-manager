import { ArchiveBoxIcon, CheckCircleIcon, XCircleIcon } from '@heroicons/react/24/outline'
import { useBackups } from '../hooks/useDashboard.js'

function StatusBadge({ status }) {
  const ok = status === 'success'
  return ok ? (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-green-900/40 text-green-400 border border-green-800">
      <CheckCircleIcon className="w-3 h-3" /> {status}
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-red-900/40 text-red-400 border border-red-800">
      <XCircleIcon className="w-3 h-3" /> {status}
    </span>
  )
}

async function triggerBackup() {
  if (!window.confirm('Start a backup now?')) return
  try {
    const r = await fetch('/api/backup/now', { method: 'POST' })
    if (r.ok) {
      window.alert('Backup started!')
    } else {
      window.alert('Failed to start backup.')
    }
  } catch {
    window.alert('Failed to start backup.')
  }
}

export default function BackupsCard() {
  const { data, isLoading } = useBackups()
  const history = (data?.history ?? []).slice(0, 3)

  return (
    <div className="bg-immich-surface border border-immich-border rounded-2xl p-5 flex flex-col">
      <h2 className="text-xs font-semibold uppercase tracking-wider text-immich-muted mb-4">Backups</h2>
      {isLoading ? (
        <p className="text-immich-muted text-sm">Loading…</p>
      ) : history.length === 0 ? (
        <p className="text-immich-muted text-sm mb-4">No backups yet</p>
      ) : (
        <div className="space-y-2 mb-4 flex-1">
          {history.map((b, i) => (
            <div key={i} className="flex items-center justify-between">
              <span className="text-xs text-immich-muted">
                {new Date(b.timestamp).toLocaleDateString()}
              </span>
              <StatusBadge status={b.status} />
            </div>
          ))}
        </div>
      )}
      <button
        onClick={triggerBackup}
        className="mt-auto w-full px-4 py-2 bg-immich-primary hover:bg-blue-600 text-white rounded-lg text-sm font-medium transition-colors duration-150 flex items-center justify-center gap-2"
      >
        <ArchiveBoxIcon className="w-4 h-4" />
        Backup Now
      </button>
    </div>
  )
}
