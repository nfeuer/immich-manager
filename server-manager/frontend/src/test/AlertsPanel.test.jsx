import { describe, it, expect, vi } from 'vitest'
import React from 'react'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import AlertsPanel from '../components/AlertsPanel.jsx'

vi.mock('../hooks/useDashboard.js', () => ({ useAlerts: vi.fn() }))
import { useAlerts } from '../hooks/useDashboard.js'

const wrapper = ({ children }) =>
  React.createElement(QueryClientProvider, { client: new QueryClient() }, children)

describe('AlertsPanel', () => {
  it('renders nothing when there are no alerts', () => {
    useAlerts.mockReturnValue({ data: { alerts: [] } })
    const { container } = render(React.createElement(AlertsPanel), { wrapper })
    expect(container.innerHTML).toBe('')
  })

  it('renders nothing when data is undefined', () => {
    useAlerts.mockReturnValue({ data: undefined })
    const { container } = render(React.createElement(AlertsPanel), { wrapper })
    expect(container.innerHTML).toBe('')
  })

  it('renders alert messages with category', () => {
    useAlerts.mockReturnValue({
      data: {
        alerts: [
          { timestamp: '2026-04-01T10:00:00Z', category: 'Disk', message: 'Disk usage high', severity: 'warning' },
        ],
      },
    })
    render(React.createElement(AlertsPanel), { wrapper })
    expect(screen.getByText(/Disk:/)).toBeInTheDocument()
    expect(screen.getByText(/Disk usage high/)).toBeInTheDocument()
  })

  it('shows at most 5 alerts', () => {
    const alerts = Array.from({ length: 8 }, (_, i) => ({
      timestamp: `2026-04-0${i + 1}T10:00:00Z`,
      category: 'Test',
      message: `Alert ${i}`,
      severity: 'info',
    }))
    useAlerts.mockReturnValue({ data: { alerts } })
    render(React.createElement(AlertsPanel), { wrapper })
    expect(screen.getAllByText(/Test:/)).toHaveLength(5)
  })

  it('applies critical severity styling', () => {
    useAlerts.mockReturnValue({
      data: {
        alerts: [
          { timestamp: '2026-04-01T10:00:00Z', category: 'CPU', message: 'Overheating', severity: 'critical' },
        ],
      },
    })
    const { container } = render(React.createElement(AlertsPanel), { wrapper })
    expect(container.querySelector('.bg-red-900\\/20')).toBeInTheDocument()
  })

  it('applies warning severity styling', () => {
    useAlerts.mockReturnValue({
      data: {
        alerts: [
          { timestamp: '2026-04-01T10:00:00Z', category: 'Mem', message: 'High usage', severity: 'warning' },
        ],
      },
    })
    const { container } = render(React.createElement(AlertsPanel), { wrapper })
    expect(container.querySelector('.bg-yellow-900\\/20')).toBeInTheDocument()
  })
})
