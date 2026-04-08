import { BellAlertIcon } from '@heroicons/react/24/outline'
import { useAlerts } from '../hooks/useDashboard.js'

const SEVERITY_STYLES = {
  critical: 'bg-immich-error-muted text-immich-error border-immich-error-border',
  warning: 'bg-immich-warning-muted text-immich-warning border-immich-warning-border',
  info: 'bg-immich-info-muted text-immich-info border-immich-info-border',
}

export default function AlertsPanel() {
  const { data } = useAlerts()
  const alerts = (data?.alerts ?? []).slice(0, 5)

  if (alerts.length === 0) return null

  return (
    <div className="bg-immich-surface border border-immich-border rounded-2xl p-5 mb-6">
      <h2 className="text-sm font-semibold text-immich-text mb-4 flex items-center gap-1.5">
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
