import { CircleStackIcon, CheckCircleIcon, ExclamationTriangleIcon } from '@heroicons/react/24/outline'
import { useDisks } from '../hooks/useDashboard.js'
import StatusBadge from './StatusBadge.jsx'
import Skeleton from './Skeleton.jsx'

function SmartBadge({ pass }) {
  return (
    <StatusBadge variant={pass ? 'success' : 'error'}>
      {pass
        ? <><CheckCircleIcon className="w-3 h-3" /> OK</>
        : <><ExclamationTriangleIcon className="w-3 h-3" /> Fail</>
      }
    </StatusBadge>
  )
}

export default function DiskHealthCard() {
  const { data, isLoading } = useDisks()
  const disks = data?.disks ?? []

  return (
    <div className="bg-immich-surface border border-immich-border rounded-2xl p-5">
      <h2 className="text-sm font-semibold text-immich-text mb-4">Disk Health</h2>
      {isLoading ? (
        <div className="space-y-3">
          {[0, 1].map((i) => (
            <div key={i} className="flex items-center justify-between">
              <Skeleton height="0.75rem" width="45%" />
              <Skeleton height="1.25rem" width="3.5rem" />
            </div>
          ))}
        </div>
      ) : disks.length === 0 ? (
        <p className="text-immich-muted text-sm">No disk data</p>
      ) : (
        <div className="space-y-3">
          {disks.map((disk) => (
            <div key={disk.device} className="flex items-center justify-between">
              <div className="flex items-center gap-1.5 min-w-0">
                <CircleStackIcon className="w-3.5 h-3.5 text-immich-muted flex-shrink-0" />
                <span className="text-xs font-mono text-immich-text truncate">{disk.device}</span>
                {disk.temperature != null && (
                  <span className="text-xs text-immich-muted ml-1">{Number(disk.temperature)}°C</span>
                )}
              </div>
              <SmartBadge pass={disk.smart_status} />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
