import { describe, it, expect, vi } from 'vitest'
import React from 'react'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import Header from '../components/Header.jsx'

vi.mock('../hooks/useDashboard.js', () => ({ useLastRefreshed: vi.fn() }))
import { useLastRefreshed } from '../hooks/useDashboard.js'

const wrapper = ({ children }) =>
  React.createElement(QueryClientProvider, { client: new QueryClient() }, children)

describe('Header', () => {
  it('renders the Server Manager title', () => {
    useLastRefreshed.mockReturnValue(0)
    render(React.createElement(Header), { wrapper })
    expect(screen.getByText('Server Manager')).toBeInTheDocument()
  })

  it('renders the subtitle', () => {
    useLastRefreshed.mockReturnValue(0)
    render(React.createElement(Header), { wrapper })
    expect(screen.getByText(/Monitoring/)).toBeInTheDocument()
  })

  it('shows "Updated never" when no data has been fetched', () => {
    useLastRefreshed.mockReturnValue(0)
    render(React.createElement(Header), { wrapper })
    expect(screen.getByText(/Updated never/)).toBeInTheDocument()
  })

  it('shows "Updated just now" for a recent refresh', () => {
    useLastRefreshed.mockReturnValue(Date.now())
    render(React.createElement(Header), { wrapper })
    expect(screen.getByText(/Updated just now/)).toBeInTheDocument()
  })
})
