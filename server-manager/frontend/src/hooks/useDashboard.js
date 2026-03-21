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
