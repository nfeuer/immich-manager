import { describe, it, expect, vi, beforeEach } from 'vitest'
import React from 'react'
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react'
import UpdateManagement from '../components/UpdateManagement.jsx'

beforeEach(() => {
  if (!HTMLDialogElement.prototype.showModal) {
    HTMLDialogElement.prototype.showModal = function () { this.open = true }
    HTMLDialogElement.prototype.close = function () { this.open = false }
  }
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

  it('opens ConfirmDialog when Apply Update is clicked', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        current_version: '1.2.3', latest_version: '1.3.0',
        update_available: true, immich_reachable: true,
        changelog_url: null, history: [],
      }),
    })
    render(React.createElement(UpdateManagement))
    await waitFor(() => screen.getByRole('button', { name: /apply update/i }))
    fireEvent.click(screen.getByRole('button', { name: /apply update/i }))
    await waitFor(() => {
      const dialog = screen.getByRole('dialog')
      expect(within(dialog).getByText(/apply immich update/i)).toBeInTheDocument()
    })
  })

  it('calls /api/updates/apply when confirmed via dialog', async () => {
    global.fetch = vi.fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          current_version: '1.2.3', latest_version: '1.3.0',
          update_available: true, immich_reachable: true,
          changelog_url: null, history: [],
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ status: 'started' }),
      })
    render(React.createElement(UpdateManagement))
    await waitFor(() => screen.getByRole('button', { name: /apply update/i }))
    fireEvent.click(screen.getByRole('button', { name: /apply update/i }))
    await waitFor(() => screen.getByRole('dialog'))
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /apply update/i }))
    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith('/api/updates/apply', { method: 'POST' })
    })
  })

  it('shows inline "Already up to date." message when server returns up_to_date', async () => {
    global.fetch = vi.fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          current_version: '1.2.3', latest_version: '1.3.0',
          update_available: true, immich_reachable: true,
          changelog_url: null, history: [],
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ status: 'up_to_date' }),
      })
    render(React.createElement(UpdateManagement))
    await waitFor(() => screen.getByRole('button', { name: /apply update/i }))
    fireEvent.click(screen.getByRole('button', { name: /apply update/i }))
    await waitFor(() => screen.getByRole('dialog'))
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /apply update/i }))
    await waitFor(() => {
      expect(screen.getByRole('status')).toHaveTextContent('Already up to date.')
    })
  })

  it('shows inline error message when apply fails', async () => {
    global.fetch = vi.fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          current_version: '1.2.3', latest_version: '1.3.0',
          update_available: true, immich_reachable: true,
          changelog_url: null, history: [],
        }),
      })
      .mockResolvedValueOnce({
        ok: false,
        json: async () => ({ detail: 'Docker error' }),
      })
    render(React.createElement(UpdateManagement))
    await waitFor(() => screen.getByRole('button', { name: /apply update/i }))
    fireEvent.click(screen.getByRole('button', { name: /apply update/i }))
    await waitFor(() => screen.getByRole('dialog'))
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /apply update/i }))
    await waitFor(() => {
      expect(screen.getByRole('status')).toHaveTextContent('Failed: Docker error')
    })
  })

  it('opens warning dialog when "Update anyway" is clicked while unreachable', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        current_version: null, latest_version: '1.3.0',
        update_available: false, immich_reachable: false,
        changelog_url: null, history: [],
      }),
    })
    render(React.createElement(UpdateManagement))
    await waitFor(() => screen.getByRole('button', { name: /update anyway/i }))
    fireEvent.click(screen.getByRole('button', { name: /update anyway/i }))
    await waitFor(() => {
      const dialog = screen.getByRole('dialog')
      expect(within(dialog).getByText(/update immich while unreachable/i)).toBeInTheDocument()
    })
  })

  it('cancelling the dialog does not call /api/updates/apply', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        current_version: '1.2.3', latest_version: '1.3.0',
        update_available: true, immich_reachable: true,
        changelog_url: null, history: [],
      }),
    })
    render(React.createElement(UpdateManagement))
    await waitFor(() => screen.getByRole('button', { name: /apply update/i }))
    fireEvent.click(screen.getByRole('button', { name: /apply update/i }))
    await waitFor(() => screen.getByRole('dialog'))
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /cancel/i }))
    // Only the initial status fetch should have been called
    expect(global.fetch).toHaveBeenCalledTimes(1)
  })
})
