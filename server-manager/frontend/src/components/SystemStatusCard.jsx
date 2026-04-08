import { CpuChipIcon, CircleStackIcon, ServerIcon } from '@heroicons/react/24/outline'
import { useStatus } from '../hooks/useDashboard.js'
import { metricBarColor, metricColor } from '../utils/thresholds.js'
import Skeleton from './Skeleton.jsx'

function MetricRow({ label, icon: Icon, pct, suffix }) {
  return (
    <div className="mb-4 last:mb-0">
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-1.5 text-immich-muted text-xs font-medium uppercase tracking-wider">
          <Icon className="w-3.5 h-3.5" />
          {label}
        </div>
        <span className={`text-sm font-semibold font-mono ${metricColor(pct)}`}>
          {pct.toFixed(1)}%{suffix ? ` (${suffix})` : ''}
        </span>
      </div>
      <div className="h-1.5 bg-immich-border rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ${metricBarColor(pct)}`}
          style={{ width: `${Math.min(pct, 100)}%` }}
        />
      </div>
    </div>
  )
}

export default function SystemStatusCard() {
  const { data, isLoading } = useStatus()

  return (
    <div className="bg-immich-surface border border-immich-border rounded-2xl p-5">
      <h2 className="text-sm font-semibold text-immich-text mb-4">System</h2>
      {isLoading || !data ? (
        <div className="space-y-4">
          {[0, 1, 2].map((i) => (
            <div key={i}>
              <Skeleton className="mb-1" height="0.75rem" width="40%" />
              <Skeleton height="0.375rem" width="100%" />
            </div>
          ))}
        </div>
      ) : (
        <>
          <MetricRow label="CPU" icon={CpuChipIcon} pct={Number(data.system.cpu_percent)} />
          <MetricRow label="Memory" icon={ServerIcon} pct={Number(data.system.memory_percent)} suffix={`${Number(data.system.memory_used_gb).toFixed(1)} GB`} />
          <MetricRow label="Disk" icon={CircleStackIcon} pct={Number(data.system.disk_usage_percent)} suffix={`${Number(data.system.disk_used_gb).toFixed(1)} GB`} />
        </>
      )}
    </div>
  )
}
