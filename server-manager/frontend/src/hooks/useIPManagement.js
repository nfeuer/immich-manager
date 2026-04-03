import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'

const fetcher = (url) => fetch(url).then((r) => {
  if (!r.ok) throw new Error(`HTTP ${r.status}`)
  return r.json()
})

const poster = (url, body) => fetch(url, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
}).then((r) => {
  if (!r.ok) throw new Error(`HTTP ${r.status}`)
  return r.json()
})

const putter = (url, body) => fetch(url, {
  method: 'PUT',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
}).then((r) => {
  if (!r.ok) throw new Error(`HTTP ${r.status}`)
  return r.json()
})

const deleter = (url) => fetch(url, { method: 'DELETE' }).then((r) => {
  if (!r.ok) throw new Error(`HTTP ${r.status}`)
  return r.json()
})

export function useTrustedIPs() {
  return useQuery({
    queryKey: ['ip-gate', 'trusted'],
    queryFn: () => fetcher('/api/ip-gate/management/trusted'),
    refetchInterval: 30000,
  })
}

export function usePendingIPs() {
  return useQuery({
    queryKey: ['ip-gate', 'pending'],
    queryFn: () => fetcher('/api/ip-gate/management/pending'),
    refetchInterval: 15000,
  })
}

export function useRevokedIPs() {
  return useQuery({
    queryKey: ['ip-gate', 'revoked'],
    queryFn: () => fetcher('/api/ip-gate/management/revoked'),
  })
}

export function useConnectionLog(filters = {}) {
  const params = new URLSearchParams()
  if (filters.ip) params.set('ip', filters.ip)
  if (filters.service) params.set('service', filters.service)
  if (filters.action) params.set('action', filters.action)
  const qs = params.toString()
  return useQuery({
    queryKey: ['ip-gate', 'connections', filters],
    queryFn: () => fetcher(`/api/ip-gate/management/connections${qs ? '?' + qs : ''}`),
    refetchInterval: 15000,
  })
}

export function useApproveIP() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body) => poster('/api/ip-gate/management/approve', body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['ip-gate'] }) },
  })
}

export function useRevokeIP() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body) => poster('/api/ip-gate/management/revoke', body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['ip-gate'] }) },
  })
}

export function useUnblockIP() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body) => poster('/api/ip-gate/management/unblock', body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['ip-gate'] }) },
  })
}

export function useDeleteIP() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (ip) => deleter(`/api/ip-gate/management/${encodeURIComponent(ip)}`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['ip-gate'] }) },
  })
}

export function useUpdateIP() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ ip, ...body }) => putter(`/api/ip-gate/management/${encodeURIComponent(ip)}`, body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['ip-gate'] }) },
  })
}
