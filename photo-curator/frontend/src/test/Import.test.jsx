import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'
import Import from '../pages/Import'
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
  // Default mock covers historyQuery (GET /api/import/jobs) added in Task 4
  vi.spyOn(api, 'apiFetch').mockResolvedValue({ jobs: [] })
})

describe('Step 0: source selection', () => {
  it('renders three source cards', () => {
    wrap(<Import />)
    expect(screen.getByText('Google Photos')).toBeInTheDocument()
    expect(screen.getByText('Apple Photos')).toBeInTheDocument()
    expect(screen.getByText('iCloud Photos')).toBeInTheDocument()
  })

  it('clicking a source card advances to step 1', () => {
    wrap(<Import />)
    fireEvent.click(screen.getByText('Google Photos'))
    expect(screen.getByTestId('file-drop-zone')).toBeInTheDocument()
    expect(screen.getByTestId('selected-source-label')).toHaveTextContent('Google Photos')
  })
})

describe('Step 1: file preview', () => {
  function goToStep1() {
    wrap(<Import />)
    fireEvent.click(screen.getByText('Google Photos'))
  }

  it('renders file drop zone after source selected', () => {
    goToStep1()
    expect(screen.getByTestId('file-drop-zone')).toBeInTheDocument()
    expect(screen.getByTestId('file-input')).toBeInTheDocument()
  })

  it('Start Import button is disabled with no files', () => {
    goToStep1()
    expect(screen.getByTestId('btn-start-import')).toBeDisabled()
  })

  it('shows file count and enables button after file selection', () => {
    goToStep1()
    const input = screen.getByTestId('file-input')
    const files = [
      new File([''], 'photo1.jpg', { type: 'image/jpeg' }),
      new File([''], 'photo2.jpg', { type: 'image/jpeg' }),
    ]
    fireEvent.change(input, { target: { files } })
    expect(screen.getByText(/2 files/)).toBeInTheDocument()
    expect(screen.getByTestId('btn-start-import')).not.toBeDisabled()
  })

  it('Back button returns to step 0', () => {
    goToStep1()
    fireEvent.click(screen.getByText('← Back'))
    expect(screen.getByText('Google Photos')).toBeInTheDocument()
    expect(screen.queryByTestId('file-drop-zone')).not.toBeInTheDocument()
  })
})

describe('Step 2: upload and progress', () => {
  function selectFilesAndClickImport(mockJobStatus = 'running') {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ job_id: 42 }),
    }))
    vi.spyOn(api, 'apiFetch').mockImplementation((url) => {
      if (url.includes('/api/import/jobs/42')) {
        return Promise.resolve({
          status: mockJobStatus,
          uploaded: 5,
          duplicates: 1,
          errors: 0,
          total_files: 10,
          error_message: null,
        })
      }
      return Promise.resolve({ jobs: [] })
    })

    wrap(<Import />)
    fireEvent.click(screen.getByText('Google Photos'))
    const input = screen.getByTestId('file-input')
    fireEvent.change(input, { target: { files: [new File([''], 'photo.jpg')] } })
    fireEvent.click(screen.getByTestId('btn-start-import'))
  }

  it('calls /api/import/upload with FormData when Start Import clicked', async () => {
    selectFilesAndClickImport()
    await waitFor(() =>
      expect(vi.mocked(fetch)).toHaveBeenCalledWith(
        '/api/import/upload',
        expect.objectContaining({ method: 'POST' })
      )
    )
  })

  it('shows progress stats after upload succeeds', async () => {
    selectFilesAndClickImport()
    await waitFor(() => expect(screen.getByTestId('stat-uploaded')).toHaveTextContent('5'))
    expect(screen.getByTestId('stat-duplicates')).toHaveTextContent('1')
    expect(screen.getByTestId('stat-total')).toHaveTextContent('10')
  })

  it('shows Cancel button while job is running', async () => {
    selectFilesAndClickImport('running')
    await waitFor(() => expect(screen.getByTestId('btn-cancel')).toBeInTheDocument())
    expect(screen.queryByTestId('btn-new-import')).not.toBeInTheDocument()
  })

  it('shows New Import button when job completes', async () => {
    selectFilesAndClickImport('completed')
    await waitFor(() => expect(screen.getByTestId('btn-new-import')).toBeInTheDocument())
    expect(screen.queryByTestId('btn-cancel')).not.toBeInTheDocument()
  })

  it('shows error banner when error_message is set', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ job_id: 42 }),
    }))
    vi.spyOn(api, 'apiFetch').mockImplementation((url) => {
      if (url.includes('/api/import/jobs/42')) {
        return Promise.resolve({
          status: 'failed',
          uploaded: 0,
          duplicates: 0,
          errors: 1,
          total_files: 1,
          error_message: 'Could not read file',
        })
      }
      return Promise.resolve({ jobs: [] })
    })

    wrap(<Import />)
    fireEvent.click(screen.getByText('Google Photos'))
    const input = screen.getByTestId('file-input')
    fireEvent.change(input, { target: { files: [new File([''], 'p.jpg')] } })
    fireEvent.click(screen.getByTestId('btn-start-import'))

    await waitFor(() =>
      expect(screen.getByTestId('error-banner')).toHaveTextContent('Could not read file')
    )
  })

  it('shows upload error inline when upload fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      json: () => Promise.resolve({ detail: 'Bad request' }),
    }))
    vi.spyOn(api, 'apiFetch').mockResolvedValue({ jobs: [] })

    wrap(<Import />)
    fireEvent.click(screen.getByText('Google Photos'))
    const input = screen.getByTestId('file-input')
    fireEvent.change(input, { target: { files: [new File([''], 'p.jpg')] } })
    fireEvent.click(screen.getByTestId('btn-start-import'))

    await waitFor(() => expect(screen.getByText('Bad request')).toBeInTheDocument())
    // Still on step 1 (no progress section)
    expect(screen.queryByTestId('stat-uploaded')).not.toBeInTheDocument()
  })

  it('Cancel button fires DELETE to job endpoint', async () => {
    const mockFetch = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({ job_id: 42 }) }) // upload
      .mockResolvedValue({ ok: true, json: () => Promise.resolve({}) })                  // cancel + refetch
    vi.stubGlobal('fetch', mockFetch)
    vi.spyOn(api, 'apiFetch').mockImplementation((url) => {
      if (url.includes('/api/import/jobs/42')) {
        return Promise.resolve({
          status: 'running', uploaded: 0, duplicates: 0, errors: 0, total_files: 5, error_message: null,
        })
      }
      return Promise.resolve({ jobs: [] })
    })

    wrap(<Import />)
    fireEvent.click(screen.getByText('Google Photos'))
    fireEvent.change(screen.getByTestId('file-input'), { target: { files: [new File([''], 'p.jpg')] } })
    fireEvent.click(screen.getByTestId('btn-start-import'))

    await waitFor(() => expect(screen.getByTestId('btn-cancel')).toBeInTheDocument())
    fireEvent.click(screen.getByTestId('btn-cancel'))

    await waitFor(() =>
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/import/jobs/42',
        expect.objectContaining({ method: 'DELETE' })
      )
    )
  })
})

describe('Import history', () => {
  it('renders history list on mount', async () => {
    vi.spyOn(api, 'apiFetch').mockResolvedValue({
      jobs: [
        {
          id: 1,
          source_type: 'google',
          import_method: 'upload',
          status: 'completed',
          uploaded: 10,
          duplicates: 2,
          errors: 0,
          created_at: '2026-03-01T00:00:00Z',
        },
      ],
    })
    wrap(<Import />)
    await waitFor(() => expect(screen.getByTestId('history-list')).toBeInTheDocument())
    expect(screen.getByTestId('history-item-1')).toBeInTheDocument()
    expect(screen.getByTestId('history-item-1')).toHaveTextContent('Google Photos')
    expect(screen.getByTestId('history-item-1')).toHaveTextContent('completed')
  })

  it('shows empty state when no history', async () => {
    vi.spyOn(api, 'apiFetch').mockResolvedValue({ jobs: [] })
    wrap(<Import />)
    await waitFor(() =>
      expect(screen.getByText('No import history yet.')).toBeInTheDocument()
    )
  })
})
