import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '../utils/api'

export function useYearProgress(year) {
  return useQuery({
    queryKey: ['yearProgress', year],
    queryFn: () => apiFetch(`/api/progress/year/${year}`),
  })
}
