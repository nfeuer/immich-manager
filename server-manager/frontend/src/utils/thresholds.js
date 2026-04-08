export function metricColor(pct) {
  if (pct >= 85) return 'text-immich-error'
  if (pct >= 70) return 'text-immich-warning'
  return 'text-immich-success'
}

export function metricBarColor(pct) {
  if (pct >= 85) return 'bg-immich-error'
  if (pct >= 70) return 'bg-immich-warning'
  return 'bg-immich-success'
}
