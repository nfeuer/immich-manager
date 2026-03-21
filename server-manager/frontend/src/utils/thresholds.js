export function metricColor(pct) {
  if (pct >= 85) return 'text-red-400'
  if (pct >= 70) return 'text-yellow-400'
  return 'text-green-400'
}

export function metricBarColor(pct) {
  if (pct >= 85) return 'bg-red-500'
  if (pct >= 70) return 'bg-yellow-500'
  return 'bg-green-500'
}
