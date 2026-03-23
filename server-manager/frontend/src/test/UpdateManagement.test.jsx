import { describe, it, expect, vi, beforeEach } from 'vitest'
import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import UpdateManagement from '../components/UpdateManagement.jsx'

beforeEach(() => {
  global.EventSource = vi.fn().mockImplementation(() => ({
    onmessage: null, onerror: null, close: vi.fn(),
  }))
})

describe('UpdateManagement', () => {
  it('shows green "Up to date" badge when current', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        current_version: '1.2.3', latest_version: '1.2.3',
        update_available: false, immich_reachable: true,
        changelog_url: null, history: [],
      }),
    })
    render(React.createElement(UpdateManagement))
    await waitFor(() => expect(screen.getByText(/up to date/i)).toBeInTheDocument())
  })

  it('shows blue "Update Available" badge and Apply button when update exists', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        current_version: '1.2.3', latest_version: '1.3.0',
        update_available: true, immich_reachable: true,
        changelog_url: 'https://github.com/immich-app/immich/releases/tag/v1.3.0',
        history: [],
      }),
    })
    render(React.createElement(UpdateManagement))
    await waitFor(() => expect(screen.getByText(/update available/i)).toBeInTheDocument())
    expect(screen.getByRole('button', { name: /apply update/i })).toBeInTheDocument()
  })

  it('does not render changelog link for non-github URLs', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        current_version: '1.2.3', latest_version: '1.3.0',
        update_available: true, immich_reachable: true,
        changelog_url: 'https://evil.com/steal', history: [],
      }),
    })
    render(React.createElement(UpdateManagement))
    await waitFor(() => screen.getByText(/update available/i))
    expect(screen.queryByText(/changelog/i)).not.toBeInTheDocument()
  })

  it('shows red "Immich unreachable" badge and amber "Update anyway" button', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        current_version: null, latest_version: '1.3.0',
        update_available: false, immich_reachable: false,
        changelog_url: null, history: [],
      }),
    })
    render(React.createElement(UpdateManagement))
    await waitFor(() => expect(screen.getByText(/immich unreachable/i)).toBeInTheDocument())
    expect(screen.getByRole('button', { name: /update anyway/i })).toBeInTheDocument()
  })
})
