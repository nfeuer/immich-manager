import { describe, it, expect, vi } from 'vitest'
import React from 'react'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import DiskHealthCard from '../components/DiskHealthCard.jsx'

vi.mock('../hooks/useDashboard.js', () => ({ useDisks: vi.fn() }))
import { useDisks } from '../hooks/useDashboard.js'

const wrapper = ({ children }) =>
  React.createElement(QueryClientProvider, { client: new QueryClient() }, children)

describe('DiskHealthCard', () => {
  it('shows loading when data is undefined', () => {
    useDisks.mockReturnValue({ data: undefined, isLoading: true })
    render(React.createElement(DiskHealthCard), { wrapper })
    expect(screen.getByText(/loading/i)).toBeInTheDocument()
  })

  it('renders a green OK badge for a healthy disk', () => {
    useDisks.mockReturnValue({
      data: { disks: [{ device: '/dev/sda', smart_status: true, temperature: 38 }] },
      isLoading: false,
    })
    render(React.createElement(DiskHealthCard), { wrapper })
    expect(screen.getByText('OK')).toBeInTheDocument()
    expect(screen.getByText('/dev/sda')).toBeInTheDocument()
    expect(screen.getByText('38°C')).toBeInTheDocument()
  })

  it('renders a red Fail badge for a failing disk', () => {
    useDisks.mockReturnValue({
      data: { disks: [{ device: '/dev/sdb', smart_status: false, temperature: null }] },
      isLoading: false,
    })
    render(React.createElement(DiskHealthCard), { wrapper })
    expect(screen.getByText('Fail')).toBeInTheDocument()
  })
})
