import { describe, it, expect, vi } from 'vitest'
import React from 'react'
import { render, screen } from '@testing-library/react'
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
})
