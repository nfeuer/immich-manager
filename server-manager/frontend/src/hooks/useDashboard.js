import { useState, useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'

const fetcher = (url) => fetch(url).then((r) => {
  if (!r.ok) throw new Error(`HTTP ${r.status}`)
  return r.json()
})

export function useStatus() {
  return useQuery({ queryKey: ['status'], queryFn: () => fetcher('/api/status') })
}

export function useDisks() {
  return useQuery({ queryKey: ['disks'], queryFn: () => fetcher('/api/disks') })
}

export function useBackups() {
  return useQuery({ queryKey: ['backups'], queryFn: () => fetcher('/api/backups') })
}

export function useAlerts() {
  return useQuery({ queryKey: ['alerts'], queryFn: () => fetcher('/api/alerts') })
}

export function useGpuCurrent() {
  // Live snapshot — refresh aggressively so you can watch the numbers move.
  return useQuery({
    queryKey: ['gpu-current'],
    queryFn: () => fetcher('/api/gpu/current'),
    refetchInterval: 5000,
  })
}

export function useGpuSummary() {
  return useQuery({
    queryKey: ['gpu-summary'],
    queryFn: () => fetcher('/api/gpu/summary'),
    refetchInterval: 30_000,
  })
}

export function useGpuHistory(hours = 168) {
  return useQuery({
    queryKey: ['gpu-history', hours],
    queryFn: () => fetcher(`/api/gpu/history?hours=${hours}`),
    refetchInterval: 60_000,
  })
}

export function useBaselineCalibration(enabled = false) {
  // On-demand only — calibration is an admin "show me a recommendation"
  // action, not something to poll.
  return useQuery({
    queryKey: ['gpu-calibrate'],
    queryFn: () => fetcher('/api/gpu/calibrate-baseline?hours=24'),
    enabled,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
  })
}

// Returns the most recent dataUpdatedAt across all four polling queries.
// Uses a cache subscription so consumers re-render when any query updates.
export function useLastRefreshed() {
  const queryClient = useQueryClient()
  const [lastUpdated, setLastUpdated] = useState(0)

  useEffect(() => {
    const cache = queryClient.getQueryCache()
    const unsubscribe = cache.subscribe(() => {
      const keys = ['status', 'disks', 'backups', 'alerts']
      const timestamps = keys.map((k) => queryClient.getQueryState([k])?.dataUpdatedAt ?? 0)
      setLastUpdated(Math.max(...timestamps))
    })
    return unsubscribe
  }, [queryClient])

  return lastUpdated
}
