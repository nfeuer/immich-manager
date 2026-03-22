import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'
import AlbumCurator from '../pages/AlbumCurator'
import * as api from '../utils/api'

function wrap(ui) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        {ui}
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe('AlbumCurator', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('shows photo thumbnails after load', async () => {
    vi.spyOn(api, 'apiFetch').mockImplementation((url) => {
      if (url.includes('/raw')) return Promise.resolve({ photos: [
        { asset_id: 'a1', thumbnail_url: '/api/thumbnail/a1', width: 100, height: 100, taken_at: null }
      ], total: 1 })
      if (url.includes('/api/analyze')) return Promise.resolve({})
      return Promise.resolve({ photos: [], total: 0 })
    })
    wrap(<AlbumCurator onAuthError={() => {}} />)
    await waitFor(() => expect(screen.getByTestId('photo-a1')).toBeInTheDocument())
  })

  it('shows month/year switcher', async () => {
    vi.spyOn(api, 'apiFetch').mockResolvedValue({ photos: [], total: 0 })
    wrap(<AlbumCurator onAuthError={() => {}} />)
    // Month label visible (any month/year format)
    await waitFor(() => expect(screen.getByTestId('month-label')).toBeInTheDocument())
  })

  it('curation footer appears after AI Curate clicked', async () => {
    vi.spyOn(api, 'apiFetch').mockImplementation((url) => {
      if (url.includes('/raw')) return Promise.resolve({ photos: [
        { asset_id: 'a1', thumbnail_url: '/api/thumbnail/a1', width: 100, height: 100, taken_at: null },
        { asset_id: 'a2', thumbnail_url: '/api/thumbnail/a2', width: 100, height: 100, taken_at: null },
      ], total: 2 })
      if (url.includes('/curation/') && !url.includes('complete')) return Promise.resolve({
        suggested_asset_ids: ['a1'],
        session_id: 's1',
      })
      return Promise.resolve({})
    })
    wrap(<AlbumCurator onAuthError={() => {}} />)
    await waitFor(() => screen.getByTestId('photo-a1'))
    fireEvent.click(screen.getByText('AI Curate'))
    await waitFor(() => expect(screen.getByTestId('curation-footer')).toBeInTheDocument())
  })
})
