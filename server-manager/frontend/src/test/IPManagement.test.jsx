import { describe, it, expect, vi, beforeEach } from 'vitest'
import React from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import IPManagement from '../components/IPManagement.jsx'

vi.mock('../hooks/useIPManagement.js', () => ({
  useTrustedIPs: vi.fn(),
  usePendingIPs: vi.fn(),
  useRevokedIPs: vi.fn(),
  useConnectionLog: vi.fn(),
  useApproveIP: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useRevokeIP: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useUnblockIP: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useDeleteIP: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useUpdateIP: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}))

import {
  useTrustedIPs, usePendingIPs, useRevokedIPs, useConnectionLog,
} from '../hooks/useIPManagement.js'

const wrapper = ({ children }) =>
  React.createElement(QueryClientProvider, { client: new QueryClient() }, children)

function mockAllHooks() {
  useTrustedIPs.mockReturnValue({
    data: {
      trusted: [
        {
          ip_address: '192.168.1.10', label: 'Home', verified_by: 'admin',
          access_level: 'admin', trust_duration: 'permanent', expires_at: null,
          last_seen: '2026-04-05T12:00:00Z', connections_7d: 42,
        },
      ],
    },
    isLoading: false,
  })
  usePendingIPs.mockReturnValue({
    data: {
      pending: [
        { ip_address: '10.0.0.5', source: 'web', created_at: '2026-04-06T08:00:00Z' },
      ],
    },
    isLoading: false,
  })
  useRevokedIPs.mockReturnValue({
    data: {
      revoked: [
        { ip_address: '172.16.0.99', verified_by: 'user1', revoked_at: '2026-04-04T10:00:00Z', revoked_by: 'admin', revoke_reason: 'Suspicious' },
      ],
    },
    isLoading: false,
  })
  useConnectionLog.mockReturnValue({
    data: {
      connections: [
        { timestamp: '2026-04-06T09:00:00Z', ip_address: '192.168.1.10', service: 'server-manager', action: 'allowed', user_id: 'admin' },
      ],
    },
    isLoading: false,
  })
}

describe('IPManagement', () => {
  beforeEach(() => {
    mockAllHooks()
  })

  it('renders all 4 tab buttons', () => {
    render(React.createElement(IPManagement), { wrapper })
    expect(screen.getByRole('button', { name: 'Trusted' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Pending' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Blacklisted' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Connections' })).toBeInTheDocument()
  })

  it('shows Trusted tab content by default', () => {
    render(React.createElement(IPManagement), { wrapper })
    // Both desktop table and mobile card render the IP — either is acceptable
    expect(screen.getAllByText('192.168.1.10').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Home').length).toBeGreaterThanOrEqual(1)
  })

  it('switches to Pending tab and shows pending IPs', () => {
    render(React.createElement(IPManagement), { wrapper })
    fireEvent.click(screen.getByRole('button', { name: 'Pending' }))
    expect(screen.getByText('10.0.0.5')).toBeInTheDocument()
  })

  it('switches to Blacklisted tab and shows revoked IPs', () => {
    render(React.createElement(IPManagement), { wrapper })
    fireEvent.click(screen.getByRole('button', { name: 'Blacklisted' }))
    expect(screen.getByText('172.16.0.99')).toBeInTheDocument()
    expect(screen.getByText('Suspicious')).toBeInTheDocument()
  })

  it('switches to Connections tab and shows connection logs', () => {
    render(React.createElement(IPManagement), { wrapper })
    fireEvent.click(screen.getByRole('button', { name: 'Connections' }))
    // IP may appear in multiple tabs; connection log also shows action
    expect(screen.getAllByText('192.168.1.10').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('allowed').length).toBeGreaterThanOrEqual(1)
  })

  it('shows Edit and Revoke buttons in Trusted tab', () => {
    render(React.createElement(IPManagement), { wrapper })
    // Both desktop and mobile render action buttons — at least one of each must exist
    expect(screen.getAllByRole('button', { name: 'Edit' }).length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByRole('button', { name: 'Revoke' }).length).toBeGreaterThanOrEqual(1)
  })

  it('shows Approve and Blacklist buttons in Pending tab', () => {
    render(React.createElement(IPManagement), { wrapper })
    fireEvent.click(screen.getByRole('button', { name: 'Pending' }))
    expect(screen.getByText('Approve')).toBeInTheDocument()
    expect(screen.getByText('Blacklist')).toBeInTheDocument()
  })

  it('shows empty state when no trusted IPs', () => {
    useTrustedIPs.mockReturnValue({ data: { trusted: [] }, isLoading: false })
    render(React.createElement(IPManagement), { wrapper })
    // Both desktop table cell and mobile paragraph render the empty state text
    expect(screen.getAllByText('No trusted IPs').length).toBeGreaterThanOrEqual(1)
  })
})
