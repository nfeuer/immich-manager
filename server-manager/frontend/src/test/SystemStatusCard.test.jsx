import { describe, it, expect, vi, beforeEach } from 'vitest'
import React from 'react'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import SystemStatusCard from '../components/SystemStatusCard.jsx'

vi.mock('../hooks/useDashboard.js', () => ({
  useStatus: vi.fn(),
}))

import { useStatus } from '../hooks/useDashboard.js'

function wrapper({ children }) {
  return React.createElement(QueryClientProvider, { client: new QueryClient() }, children)
}

describe('SystemStatusCard', () => {
  it('shows loading state when data is undefined', () => {
    useStatus.mockReturnValue({ data: undefined, isLoading: true })
    render(React.createElement(SystemStatusCard), { wrapper })
    expect(screen.getByText(/loading/i)).toBeInTheDocument()
  })

  it('renders CPU percent without GB value', () => {
    useStatus.mockReturnValue({
      data: { system: { cpu_percent: 45, memory_percent: 60, memory_used_gb: 8.2, disk_usage_percent: 55, disk_used_gb: 220 } },
      isLoading: false,
    })
    render(React.createElement(SystemStatusCard), { wrapper })
    expect(screen.getByText('45.0%')).toBeInTheDocument()
    expect(screen.getByText(/60\.0%.*8\.2 GB/)).toBeInTheDocument()
  })

  it('renders red color class when CPU exceeds 85%', () => {
    useStatus.mockReturnValue({
      data: { system: { cpu_percent: 92, memory_percent: 30, memory_used_gb: 4, disk_usage_percent: 30, disk_used_gb: 100 } },
      isLoading: false,
    })
    const { container } = render(React.createElement(SystemStatusCard), { wrapper })
    expect(container.querySelector('.bg-red-500')).toBeInTheDocument()
  })
})
