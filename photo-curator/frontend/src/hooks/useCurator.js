import { useState, useEffect, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '../utils/api'

export function useCurator(year, month) {
  const queryClient = useQueryClient()

  // NOTE: TanStack Query v5 removed onError/onSuccess from useQuery.
  // Auth errors are caught by the global cache subscriber in App.jsx.

  // Step 1: raw photos — load immediately
  const rawQuery = useQuery({
    queryKey: ['rawPhotos', year, month],
    queryFn: () => apiFetch(`/api/photos/${year}/${month}/raw`),
  })

  // Step 2: trigger background analysis once raw photos are loaded
  const analyzeMutation = useMutation({
    mutationFn: () => apiFetch(`/api/analyze/${year}/${month}`, { method: 'POST' }),
  })

  useEffect(() => {
    if (!rawQuery.data || rawQuery.data.total === 0) return
    if (analyzeMutation.isSuccess || analyzeMutation.isPending) return
    // Skip if all photos are already scored
    if (rawQuery.data.scored_count >= rawQuery.data.total) return
    analyzeMutation.mutate()
  }, [rawQuery.data, analyzeMutation.isSuccess, analyzeMutation.isPending, analyzeMutation.mutate])

  // Step 3: poll scored photos to track analysis progress; stop once all are scored
  const scoredQuery = useQuery({
    queryKey: ['scoredPhotos', year, month],
    queryFn: () => apiFetch(`/api/photos/${year}/${month}`),
    refetchInterval: (query) => {
      const scored = query.state.data?.photos?.length ?? 0
      const total = rawQuery.data?.total ?? 0
      return total > 0 && scored >= total ? false : 5_000
    },
  })

  const rawTotal = rawQuery.data?.total ?? 0
  const scoredTotal = scoredQuery.data?.photos?.length ?? 0
  const analysisComplete = rawTotal > 0 && scoredTotal >= rawTotal

  // Curation state
  const [selected, setSelected] = useState(new Set())
  const [curated, setCurated] = useState(false)
  const [recommendedCount, setRecommendedCount] = useState(null)

  // AI Curate: read the already-fetched session's ai_suggested list — no extra request needed
  const aiCurateAction = useCallback(() => {
    const suggested = scoredQuery.data?.session?.ai_suggested ?? []
    setSelected(new Set(suggested))
    setRecommendedCount(suggested.length)
    setCurated(true)
  }, [scoredQuery.data])

  const togglePhoto = useCallback((assetId) => {
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(assetId)) next.delete(assetId)
      else next.add(assetId)
      return next
    })
  }, [])

  const monthName = new Date(year, month - 1).toLocaleString('en-US', { month: 'long' })
  const albumName = `${monthName} ${year}`

  const saveAlbumMutation = useMutation({
    mutationFn: () => apiFetch(`/api/curation/${year}/${month}/complete`, {
      method: 'POST',
      body: JSON.stringify({ asset_ids: [...selected], album_name: albumName }),
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['yearProgress'] })
      setCurated(false)
      setSelected(new Set())
    },
  })

  const resetCuration = useCallback(() => {
    setSelected(new Set())
    setCurated(false)
  }, [])

  return {
    photos: rawQuery.data?.photos ?? [],
    isLoading: rawQuery.isPending,
    rawTotal,
    scoredTotal,
    analysisComplete,
    selected,
    curated,
    togglePhoto,
    aiCurate: aiCurateAction,
    isCurating: false,
    saveAlbum: saveAlbumMutation.mutate,
    isSaving: saveAlbumMutation.isPending,
    resetCuration,
    recommendedCount,
  }
}
