import { BellAlertIcon } from '@heroicons/react/24/outline'
import { useAlerts } from '../hooks/useDashboard.js'

const SEVERITY_STYLES = {
  critical: 'bg-red-900/20 text-red-300 border-red-800',
  warning: 'bg-yellow-900/20 text-yellow-300 border-yellow-800',
  info: 'bg-blue-900/20 text-blue-300 border-blue-800',
}

export default function AlertsPanel() {
  const { data } = useAlerts()
  const alerts = (data?.alerts ?? []).slice(0, 5)

  if (alerts.length === 0) return null

  return (
    <div className="bg-immich-surface border border-immich-border rounded-2xl p-5 mb-6">
      <h2 className="text-xs font-semibold uppercase tracking-wider text-immich-muted mb-4 flex items-center gap-1.5">
        <BellAlertIcon className="w-3.5 h-3.5" /> Alerts
      </h2>
      <div className="space-y-2">
        {alerts.map((alert, i) => (
          <div
            key={`${alert.timestamp}-${alert.category}-${i}`}
            className={`px-3 py-2.5 rounded-lg border text-sm ${SEVERITY_STYLES[alert.severity] ?? SEVERITY_STYLES.info}`}
          >
            <span className="font-semibold">{alert.category}:</span> {alert.message}
            <span className="block text-xs mt-0.5 opacity-60">
              {new Date(alert.timestamp).toLocaleString()}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
