import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'
import Duplicates from '../pages/Duplicates'
import * as api from '../utils/api'

function wrap(ui) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  )
}

beforeEach(() => {
  vi.restoreAllMocks()
  vi.spyOn(api, 'apiFetch').mockImplementation((url) => {
    if (url === '/api/dedup/scan/status') return Promise.resolve({ status: 'idle' })
    if (url === '/api/dedup/groups') return Promise.resolve({ groups: [], total_groups: 0, total_removable_photos: 0, total_savings_bytes: 0 })
    return Promise.resolve({})
  })
})

describe('Scan Panel', () => {
  it('renders Quick Scan and Deep Scan tabs', () => {
    wrap(<Duplicates />)
    expect(screen.getByTestId('tab-quick')).toBeInTheDocument()
    expect(screen.getByTestId('tab-deep')).toBeInTheDocument()
  })

  it('Quick Scan tab is active by default', () => {
    wrap(<Duplicates />)
    expect(screen.getByTestId('tab-quick')).toHaveAttribute('aria-selected', 'true')
  })

  it('clicking Deep Scan tab shows date pickers', () => {
    wrap(<Duplicates />)
    fireEvent.click(screen.getByTestId('tab-deep'))
    expect(screen.getByTestId('input-date-from')).toBeInTheDocument()
    expect(screen.getByTestId('input-date-to')).toBeInTheDocument()
  })

  it('Start Deep Scan button is disabled without dates', () => {
    wrap(<Duplicates />)
    fireEvent.click(screen.getByTestId('tab-deep'))
    expect(screen.getByTestId('btn-start-deep')).toBeDisabled()
  })

  it('Start Deep Scan button enables after both dates selected', () => {
    wrap(<Duplicates />)
    fireEvent.click(screen.getByTestId('tab-deep'))
    fireEvent.change(screen.getByTestId('input-date-from'), { target: { value: '2024-01-01' } })
    fireEvent.change(screen.getByTestId('input-date-to'), { target: { value: '2024-12-31' } })
    expect(screen.getByTestId('btn-start-deep')).not.toBeDisabled()
  })

  it('Estimate button calls /api/dedup/scan/estimate', async () => {
    vi.spyOn(api, 'apiFetch').mockImplementation((url) => {
      if (url === '/api/dedup/scan/status') return Promise.resolve({ status: 'idle' })
      if (url === '/api/dedup/groups') return Promise.resolve({ groups: [], total_groups: 0, total_removable_photos: 0, total_savings_bytes: 0 })
      if (url === '/api/dedup/scan/estimate') return Promise.resolve({
        total_assets: 500, needs_hashing: 200, estimated_seconds: 60, warning: false,
      })
      return Promise.resolve({})
    })
    wrap(<Duplicates />)
    fireEvent.click(screen.getByTestId('tab-deep'))
    fireEvent.change(screen.getByTestId('input-date-from'), { target: { value: '2024-01-01' } })
    fireEvent.change(screen.getByTestId('input-date-to'), { target: { value: '2024-12-31' } })
    fireEvent.click(screen.getByTestId('btn-estimate'))
    await waitFor(() => expect(screen.getByTestId('estimate-result')).toBeInTheDocument())
    expect(screen.getByTestId('estimate-result')).toHaveTextContent('500')
  })

  it('shows warning banner when estimate warning is true', async () => {
    vi.spyOn(api, 'apiFetch').mockImplementation((url) => {
      if (url === '/api/dedup/scan/status') return Promise.resolve({ status: 'idle' })
      if (url === '/api/dedup/groups') return Promise.resolve({ groups: [], total_groups: 0, total_removable_photos: 0, total_savings_bytes: 0 })
      if (url === '/api/dedup/scan/estimate') return Promise.resolve({
        total_assets: 2000, needs_hashing: 800, estimated_seconds: 240, warning: true,
      })
      return Promise.resolve({})
    })
    wrap(<Duplicates />)
    fireEvent.click(screen.getByTestId('tab-deep'))
    fireEvent.change(screen.getByTestId('input-date-from'), { target: { value: '2023-01-01' } })
    fireEvent.change(screen.getByTestId('input-date-to'), { target: { value: '2024-12-31' } })
    fireEvent.click(screen.getByTestId('btn-estimate'))
    await waitFor(() => expect(screen.getByTestId('estimate-warning')).toBeInTheDocument())
  })

  it('shows progress bar when scan is running (hashing phase)', async () => {
    vi.spyOn(api, 'apiFetch').mockImplementation((url) => {
      if (url === '/api/dedup/scan/status') return Promise.resolve({
        status: 'running', phase: 'hashing', hashed: 50, total_assets: 200,
        mode: 'deep', scan_id: 'x', groups_found: 0,
      })
      if (url === '/api/dedup/groups') return Promise.resolve({ groups: [], total_groups: 0, total_removable_photos: 0, total_savings_bytes: 0 })
      return Promise.resolve({})
    })
    wrap(<Duplicates />)
    await waitFor(() => expect(screen.getByTestId('scan-progress')).toBeInTheDocument())
    expect(screen.getByTestId('scan-progress')).toHaveTextContent('50')
    expect(screen.getByTestId('btn-cancel-scan')).toBeInTheDocument()
  })
})

describe('Results Panel', () => {
  it('shows empty state when no groups', async () => {
    wrap(<Duplicates />)
    await waitFor(() => expect(screen.getByTestId('no-groups-message')).toBeInTheDocument())
  })

  it('renders group cards when groups exist', async () => {
    vi.spyOn(api, 'apiFetch').mockImplementation((url) => {
      if (url === '/api/dedup/scan/status') return Promise.resolve({ status: 'complete' })
      if (url.startsWith('/api/dedup/groups')) return Promise.resolve({
        groups: [{
          id: 1, resolved: false, recommended_keep_id: 'a1',
          asset_ids: JSON.stringify(['a1', 'a2']),
          savings_bytes: 2100000,
          assets: [
            { asset_id: 'a1', thumbnail_url: '/api/thumbnail/a1', width: 4032, height: 3024, file_size_bytes: 4200000, megapixels: 12.2, filename: 'good.jpg', date_taken: '2024-01-01', camera_model: 'iPhone 15' },
            { asset_id: 'a2', thumbnail_url: '/api/thumbnail/a2', width: 2000, height: 1500, file_size_bytes: 2100000, megapixels: 3.0, filename: 'small.jpg', date_taken: '2024-01-01', camera_model: null },
          ],
        }],
        total_groups: 1,
        total_removable_photos: 1,
        total_savings_bytes: 2100000,
      })
      return Promise.resolve({})
    })
    wrap(<Duplicates />)
    await waitFor(() => expect(screen.getByTestId('group-card-1')).toBeInTheDocument())
    expect(screen.getByTestId('recommended-badge')).toBeInTheDocument()
  })

  it('clicking group card opens detail view', async () => {
    vi.spyOn(api, 'apiFetch').mockImplementation((url) => {
      if (url === '/api/dedup/scan/status') return Promise.resolve({ status: 'complete' })
      if (url.startsWith('/api/dedup/groups')) return Promise.resolve({
        groups: [{
          id: 1, resolved: false, recommended_keep_id: 'a1',
          asset_ids: JSON.stringify(['a1', 'a2']),
          savings_bytes: 2100000,
          assets: [
            { asset_id: 'a1', thumbnail_url: '/api/thumbnail/a1', width: 4032, height: 3024, file_size_bytes: 4200000, megapixels: 12.2, filename: 'good.jpg', date_taken: '2024-01-01', camera_model: 'iPhone 15' },
            { asset_id: 'a2', thumbnail_url: '/api/thumbnail/a2', width: 2000, height: 1500, file_size_bytes: 2100000, megapixels: 3.0, filename: 'small.jpg', date_taken: '2024-01-01', camera_model: null },
          ],
        }],
        total_groups: 1,
        total_removable_photos: 1,
        total_savings_bytes: 2100000,
      })
      return Promise.resolve({})
    })
    wrap(<Duplicates />)
    await waitFor(() => screen.getByTestId('group-card-1'))
    fireEvent.click(screen.getByTestId('group-card-1'))
    await waitFor(() => expect(screen.getByTestId('detail-panel')).toBeInTheDocument())
    expect(screen.getByTestId('btn-delete-others')).toBeInTheDocument()
  })
})
