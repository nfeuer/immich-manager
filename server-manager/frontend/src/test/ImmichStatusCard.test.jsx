import { describe, it, expect, vi } from 'vitest'
import React from 'react'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import ImmichStatusCard from '../components/ImmichStatusCard.jsx'

vi.mock('../hooks/useDashboard.js', () => ({ useStatus: vi.fn() }))
import { useStatus } from '../hooks/useDashboard.js'

const wrapper = ({ children }) =>
  React.createElement(QueryClientProvider, { client: new QueryClient() }, children)

describe('ImmichStatusCard', () => {
  it('shows loading state when data is undefined', () => {
    useStatus.mockReturnValue({ data: undefined, isLoading: true })
    const { container } = render(React.createElement(ImmichStatusCard), { wrapper })
    expect(container.querySelector('[aria-hidden="true"].animate-pulse')).toBeInTheDocument()
  })

  it('renders green Healthy badge when immich is healthy', () => {
    useStatus.mockReturnValue({
      data: { immich_healthy: true, containers: [{ name: 'immich_server' }, { name: 'immich_ml' }] },
      isLoading: false,
    })
    render(React.createElement(ImmichStatusCard), { wrapper })
    expect(screen.getByText('Healthy')).toBeInTheDocument()
  })

  it('renders red Issues Detected badge when immich is unhealthy', () => {
    useStatus.mockReturnValue({
      data: { immich_healthy: false, containers: [{ name: 'immich_server' }] },
      isLoading: false,
    })
    render(React.createElement(ImmichStatusCard), { wrapper })
    expect(screen.getByText('Issues Detected')).toBeInTheDocument()
  })

  it('displays container count', () => {
    useStatus.mockReturnValue({
      data: { immich_healthy: true, containers: [{ name: 'a' }, { name: 'b' }, { name: 'c' }] },
      isLoading: false,
    })
    render(React.createElement(ImmichStatusCard), { wrapper })
    expect(screen.getByText('3 running')).toBeInTheDocument()
  })
})
