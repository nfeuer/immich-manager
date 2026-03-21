import { describe, it, expect, vi, beforeEach } from 'vitest'
import React from 'react'
import { renderHook, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useLastRefreshed } from '../hooks/useDashboard.js'

function makeWrapper(client) {
  return ({ children }) => React.createElement(QueryClientProvider, { client }, children)
}

describe('useLastRefreshed', () => {
  it('returns 0 when no queries have fetched', () => {
    const client = new QueryClient()
    const { result } = renderHook(() => useLastRefreshed(), { wrapper: makeWrapper(client) })
    expect(result.current).toBe(0)
  })

  it('updates when a query cache entry is written', async () => {
    const client = new QueryClient()
    const { result } = renderHook(() => useLastRefreshed(), { wrapper: makeWrapper(client) })
    expect(result.current).toBe(0)

    const before = Date.now()
    act(() => {
      client.setQueryData(['status'], { system: {} })
    })

    expect(result.current).toBeGreaterThanOrEqual(before)
  })
})
