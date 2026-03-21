import { CheckCircleIcon, ExclamationCircleIcon, CubeIcon } from '@heroicons/react/24/outline'
import { useStatus } from '../hooks/useDashboard.js'

function HealthBadge({ healthy }) {
  return healthy ? (
    <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-900/40 text-green-400 border border-green-800">
      <CheckCircleIcon className="w-3.5 h-3.5" /> Healthy
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-900/40 text-red-400 border border-red-800">
      <ExclamationCircleIcon className="w-3.5 h-3.5" /> Issues Detected
    </span>
  )
}

export default function ImmichStatusCard() {
  const { data, isLoading } = useStatus()

  return (
    <div className="bg-immich-surface border border-immich-border rounded-2xl p-5">
      <h2 className="text-xs font-semibold uppercase tracking-wider text-immich-muted mb-4">Immich</h2>
      {isLoading || !data ? (
        <p className="text-immich-muted text-sm">Loading…</p>
      ) : (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs text-immich-muted">Service Health</span>
            <HealthBadge healthy={data.immich_healthy} />
          </div>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5 text-xs text-immich-muted">
              <CubeIcon className="w-3.5 h-3.5" /> Containers
            </div>
            <span className="text-sm font-medium text-immich-text">{data.containers.length} running</span>
          </div>
        </div>
      )}
    </div>
  )
}
