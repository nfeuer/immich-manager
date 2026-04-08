const VARIANT_CLASSES = {
  success: 'bg-immich-success-muted text-immich-success border-immich-success-border',
  error: 'bg-immich-error-muted text-immich-error border-immich-error-border',
  warning: 'bg-immich-warning-muted text-immich-warning border-immich-warning-border',
  info: 'bg-immich-info-muted text-immich-info border-immich-info-border',
}

export default function StatusBadge({ variant = 'info', children }) {
  return (
    <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium border ${VARIANT_CLASSES[variant] ?? VARIANT_CLASSES.info}`}>
      {children}
    </span>
  )
}
