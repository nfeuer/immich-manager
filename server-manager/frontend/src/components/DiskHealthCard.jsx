import {
  CircleStackIcon,
  CheckCircleIcon,
  ExclamationTriangleIcon,
  MoonIcon,
} from '@heroicons/react/24/outline'
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

function tempColor(temp, type) {
  if (temp == null) return 'text-immich-muted'
  // Match per-type warn thresholds in config defaults — keep this in sync.
  const warn = type === 'nvme' ? 70 : type === 'ssd' ? 60 : 45
  if (temp >= warn) return 'text-immich-warning'
  return 'text-immich-muted'
}

function isStandby(power_state) {
  if (!power_state) return false
  const s = String(power_state).toLowerCase()
  return s.includes('standby') || s.includes('sleep')
}

function WearBar({ wear }) {
  if (wear == null) return null
  const tone =
    wear >= 90 ? 'bg-immich-error' : wear >= 70 ? 'bg-immich-warning' : 'bg-immich-info'
  return (
    <div
      className="w-12 h-1 bg-immich-border rounded-full overflow-hidden"
      title={`NVMe wear: ${wear}% used`}
    >
      <div className={`h-full ${tone}`} style={{ width: `${Math.min(100, wear)}%` }} />
    </div>
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
        <div className="space-y-2.5">
          {disks.map((disk) => (
            <div key={disk.device} className="space-y-0.5">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-1.5 min-w-0 flex-1">
                  {isStandby(disk.power_state) ? (
                    <MoonIcon
                      className="w-3.5 h-3.5 text-immich-muted flex-shrink-0"
                      title="Drive in standby"
                    />
                  ) : (
                    <CircleStackIcon className="w-3.5 h-3.5 text-immich-muted flex-shrink-0" />
                  )}
                  <span className="text-xs font-mono text-immich-text truncate">
                    {disk.device}
                  </span>
                  {disk.drive_type && (
                    <span className="text-[10px] uppercase text-immich-muted/70 font-mono">
                      {disk.drive_type}
                    </span>
                  )}
                  {disk.temperature != null && (
                    <span className={`text-xs font-mono ${tempColor(disk.temperature, disk.drive_type)}`}>
                      {Number(disk.temperature)}°C
                    </span>
                  )}
                </div>
                <SmartBadge pass={disk.smart_status} />
              </div>
              {/* Secondary line surfaces NVMe wear, lifetime writes, and power state.
                  Hidden when no info is available so the card stays compact. */}
              {(disk.wear_percent != null ||
                disk.tb_written != null ||
                isStandby(disk.power_state)) && (
                <div className="flex items-center justify-between gap-2 pl-5 text-[10px] text-immich-muted font-mono">
                  <div className="flex items-center gap-2">
                    {isStandby(disk.power_state) && (
                      <span className="text-immich-info">{String(disk.power_state).toLowerCase()}</span>
                    )}
                    {disk.tb_written != null && <span>{disk.tb_written.toFixed(1)} TB written</span>}
                    {disk.power_on_hours != null && (
                      <span>{Math.round(disk.power_on_hours / 24 / 30)} mo on</span>
                    )}
                  </div>
                  {disk.wear_percent != null && (
                    <div className="flex items-center gap-1.5">
                      <span>{disk.wear_percent}% wear</span>
                      <WearBar wear={disk.wear_percent} />
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
