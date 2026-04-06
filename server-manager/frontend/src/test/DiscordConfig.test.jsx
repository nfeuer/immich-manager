import { describe, it, expect, vi } from 'vitest'
import React from 'react'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import DiscordConfig from '../components/DiscordConfig.jsx'

vi.mock('../hooks/useDiscordConfig.js', () => ({
  useDiscordConfig: vi.fn(),
  useUpdateDiscordConfig: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
  useTestAlert: vi.fn(() => ({ mutate: vi.fn(), isPending: false, isSuccess: false, isError: false })),
  useTestDigest: vi.fn(() => ({ mutate: vi.fn(), isPending: false, isSuccess: false, isError: false })),
}))

import { useDiscordConfig } from '../hooks/useDiscordConfig.js'

const wrapper = ({ children }) =>
  React.createElement(QueryClientProvider, { client: new QueryClient() }, children)

describe('DiscordConfig', () => {
  it('shows loading state', () => {
    useDiscordConfig.mockReturnValue({ data: undefined, isLoading: true, isError: false })
    render(React.createElement(DiscordConfig), { wrapper })
    expect(screen.getByText('Loading...')).toBeInTheDocument()
  })

  it('shows error state', () => {
    useDiscordConfig.mockReturnValue({ data: undefined, isLoading: false, isError: true })
    render(React.createElement(DiscordConfig), { wrapper })
    expect(screen.getByText(/Failed to load Discord configuration/)).toBeInTheDocument()
  })

  it('renders Discord Alerts section with form fields', () => {
    useDiscordConfig.mockReturnValue({
      data: {
        discord: { enabled: true, webhook_url: 'https://discord.com/api/webhooks/test', bot_name: 'Bot', server_name: 'Home' },
        digest: { enabled: false, schedule: '0 9 * * *', sections: ['system'] },
        quiet_hours: { enabled: true, start: '22:00', end: '08:00' },
      },
      isLoading: false,
      isError: false,
    })
    render(React.createElement(DiscordConfig), { wrapper })
    expect(screen.getByText('Discord Alerts')).toBeInTheDocument()
    expect(screen.getByText('Discord Digest')).toBeInTheDocument()
    expect(screen.getByText('Quiet Hours')).toBeInTheDocument()
    expect(screen.getByPlaceholderText(/discord.com\/api\/webhooks/)).toBeInTheDocument()
  })

  it('renders all 5 digest section checkboxes', () => {
    useDiscordConfig.mockReturnValue({
      data: {
        discord: { enabled: false, webhook_url: '', bot_name: '', server_name: '' },
        digest: { enabled: true, schedule: '0 9 * * *', sections: ['system', 'storage', 'backups', 'containers', 'alerts'] },
        quiet_hours: { enabled: false, start: '22:00', end: '08:00' },
      },
      isLoading: false,
      isError: false,
    })
    render(React.createElement(DiscordConfig), { wrapper })
    // Text is lowercase in DOM; CSS `capitalize` handles display
    expect(screen.getByText('system')).toBeInTheDocument()
    expect(screen.getByText('storage')).toBeInTheDocument()
    expect(screen.getByText('backups')).toBeInTheDocument()
    expect(screen.getByText('containers')).toBeInTheDocument()
    // "alerts" text also appears in section headings — use getAllByText
    expect(screen.getAllByText('alerts').length).toBeGreaterThanOrEqual(1)
  })

  it('renders Save button disabled when form is not dirty', () => {
    useDiscordConfig.mockReturnValue({
      data: {
        discord: { enabled: false, webhook_url: '', bot_name: '', server_name: '' },
        digest: { enabled: false, schedule: '0 9 * * *', sections: [] },
        quiet_hours: { enabled: false, start: '22:00', end: '08:00' },
      },
      isLoading: false,
      isError: false,
    })
    render(React.createElement(DiscordConfig), { wrapper })
    const saveBtn = screen.getByRole('button', { name: /save changes/i })
    expect(saveBtn).toBeDisabled()
  })

  it('renders Test Alert button disabled when discord is not enabled', () => {
    useDiscordConfig.mockReturnValue({
      data: {
        discord: { enabled: false, webhook_url: '', bot_name: '', server_name: '' },
        digest: { enabled: false, schedule: '0 9 * * *', sections: [] },
        quiet_hours: { enabled: false, start: '22:00', end: '08:00' },
      },
      isLoading: false,
      isError: false,
    })
    render(React.createElement(DiscordConfig), { wrapper })
    const testBtn = screen.getByRole('button', { name: /test alert/i })
    expect(testBtn).toBeDisabled()
  })
})
