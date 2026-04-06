import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'

const fetcher = (url) => fetch(url).then((r) => {
  if (!r.ok) throw new Error(`HTTP ${r.status}`)
  return r.json()
})

const poster = (url, body) => fetch(url, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: body ? JSON.stringify(body) : undefined,
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

export function useDiscordConfig() {
  return useQuery({
    queryKey: ['discord-config'],
    queryFn: () => fetcher('/api/config/discord'),
  })
}

export function useUpdateDiscordConfig() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body) => putter('/api/config/discord', body),
    onSuccess: (data) => { qc.setQueryData(['discord-config'], data) },
  })
}

export function useTestAlert() {
  return useMutation({
    mutationFn: () => poster('/api/test-alert'),
  })
}

export function useTestDigest() {
  return useMutation({
    mutationFn: () => poster('/api/digest/trigger'),
  })
}
