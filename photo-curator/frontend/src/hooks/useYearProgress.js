import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '../utils/api'

// NOTE: TanStack Query v5 removed the `onError` option from useQuery.
// Auth errors (AuthError) from all queries are caught by the global
// query cache subscriber wired up in App.jsx — no per-query onError needed.
export function useYearProgress(year) {
  return useQuery({
    queryKey: ['yearProgress', year],
    queryFn: () => apiFetch(`/api/progress/year/${year}`),
  })
}
