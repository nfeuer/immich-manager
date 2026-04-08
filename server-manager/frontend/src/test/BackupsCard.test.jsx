import { describe, it, expect, vi, beforeEach } from 'vitest'
import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import BackupsCard from '../components/BackupsCard.jsx'

vi.mock('../hooks/useDashboard.js', () => ({ useBackups: vi.fn() }))
import { useBackups } from '../hooks/useDashboard.js'

const wrapper = ({ children }) =>
  React.createElement(QueryClientProvider, { client: new QueryClient() }, children)

describe('BackupsCard', () => {
  it('renders green badge for successful backup', () => {
    useBackups.mockReturnValue({
      data: { history: [{ timestamp: '2026-03-01T12:00:00Z', status: 'success' }] },
      isLoading: false,
    })
    render(React.createElement(BackupsCard), { wrapper })
    expect(screen.getByText('success')).toBeInTheDocument()
  })

  it('renders red badge for failed backup', () => {
    useBackups.mockReturnValue({
      data: { history: [{ timestamp: '2026-03-01T12:00:00Z', status: 'failed' }] },
      isLoading: false,
    })
    render(React.createElement(BackupsCard), { wrapper })
    expect(screen.getByText('failed')).toBeInTheDocument()
  })

  it('shows at most 3 history entries', () => {
    useBackups.mockReturnValue({
      data: {
        history: Array.from({ length: 5 }, (_, i) => ({
          timestamp: `2026-03-0${i + 1}T12:00:00Z`,
          status: 'success',
        })),
      },
      isLoading: false,
    })
    render(React.createElement(BackupsCard), { wrapper })
    expect(screen.getAllByText('success')).toHaveLength(3)
  })

  it('arms on first click, showing confirm label', () => {
    useBackups.mockReturnValue({ data: { history: [] }, isLoading: false })
    render(React.createElement(BackupsCard), { wrapper })
    const btn = screen.getByRole('button', { name: /start backup now/i })
    fireEvent.click(btn)
    expect(screen.getByText('Click again to confirm')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /confirm start backup/i })).toBeInTheDocument()
  })

  it('triggers fetch and shows success message on second click', async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: true })
    useBackups.mockReturnValue({ data: { history: [] }, isLoading: false })
    render(React.createElement(BackupsCard), { wrapper })

    const btn = screen.getByRole('button', { name: /start backup now/i })
    fireEvent.click(btn)
    fireEvent.click(screen.getByRole('button', { name: /confirm start backup/i }))

    await waitFor(() => {
      expect(screen.getByRole('status')).toHaveTextContent('Backup started!')
    })
    expect(global.fetch).toHaveBeenCalledWith('/api/backup/now', { method: 'POST' })
  })

  it('shows error message when fetch fails', async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: false })
    useBackups.mockReturnValue({ data: { history: [] }, isLoading: false })
    render(React.createElement(BackupsCard), { wrapper })

    fireEvent.click(screen.getByRole('button', { name: /start backup now/i }))
    fireEvent.click(screen.getByRole('button', { name: /confirm start backup/i }))

    await waitFor(() => {
      expect(screen.getByRole('status')).toHaveTextContent('Failed to start backup.')
    })
  })

  it('shows error message when fetch throws', async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error('network'))
    useBackups.mockReturnValue({ data: { history: [] }, isLoading: false })
    render(React.createElement(BackupsCard), { wrapper })

    fireEvent.click(screen.getByRole('button', { name: /start backup now/i }))
    fireEvent.click(screen.getByRole('button', { name: /confirm start backup/i }))

    await waitFor(() => {
      expect(screen.getByRole('status')).toHaveTextContent('Failed to start backup.')
    })
  })
})
