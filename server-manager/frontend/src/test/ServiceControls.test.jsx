import { describe, it, expect, vi, beforeEach } from 'vitest'
import React from 'react'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import ServiceControls from '../components/ServiceControls.jsx'

beforeEach(() => {
  global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) })
  if (!HTMLDialogElement.prototype.showModal) {
    HTMLDialogElement.prototype.showModal = function () { this.open = true }
    HTMLDialogElement.prototype.close = function () { this.open = false }
  }
})

describe('ServiceControls', () => {
  it('renders all 6 expected services', () => {
    render(React.createElement(ServiceControls))
    expect(screen.getByText('immich_server')).toBeInTheDocument()
    expect(screen.getByText('immich_machine_learning')).toBeInTheDocument()
    expect(screen.getByText('immich_postgres')).toBeInTheDocument()
    expect(screen.getByText('immich_redis')).toBeInTheDocument()
    expect(screen.getByText('server_manager')).toBeInTheDocument()
    expect(screen.getByText('photo_curator')).toBeInTheDocument()
  })

  it('does not render the "system" service', () => {
    render(React.createElement(ServiceControls))
    expect(screen.queryByText('system')).not.toBeInTheDocument()
  })

  it('arms the restart button on first click (shows Confirm?)', async () => {
    render(React.createElement(ServiceControls))
    const btn = screen.getByRole('button', { name: /^restart immich_server$/i })
    fireEvent.click(btn)
    // After first click the button should be armed
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /confirm restart immich_server/i })).toBeInTheDocument()
    })
    // fetch should NOT have been called yet
    expect(global.fetch).not.toHaveBeenCalled()
  })

  it('calls POST /api/services/{service}/restart when a restart button is clicked twice', async () => {
    render(React.createElement(ServiceControls))
    const btn = screen.getByRole('button', { name: /^restart immich_server$/i })
    // First click — arms
    fireEvent.click(btn)
    // Second click — fires (button label has changed to "Confirm restart immich_server")
    await act(async () => {
      const armedBtn = screen.getByRole('button', { name: /confirm restart immich_server/i })
      fireEvent.click(armedBtn)
    })
    expect(global.fetch).toHaveBeenCalledWith(
      '/api/services/immich_server/restart',
      { method: 'POST' }
    )
  })

  it('opens ConfirmDialog when "Restart All Immich Services" is clicked', async () => {
    render(React.createElement(ServiceControls))
    const triggerBtn = screen.getByRole('button', { name: /restart all immich services/i })
    fireEvent.click(triggerBtn)
    await waitFor(() => {
      expect(screen.getByText('Restart all Immich services?')).toBeInTheDocument()
    })
  })

  it('calls POST /api/services/restart-all when confirmed in the dialog', async () => {
    render(React.createElement(ServiceControls))
    // Open the dialog
    fireEvent.click(screen.getByRole('button', { name: /restart all immich services/i }))
    // Click the confirm button inside the dialog (exact match to avoid matching trigger button)
    await act(async () => {
      const confirmBtn = screen.getByRole('button', { name: /^restart all$/i })
      fireEvent.click(confirmBtn)
    })
    expect(global.fetch).toHaveBeenCalledWith('/api/services/restart-all', { method: 'POST' })
  })

  it('shows success banner after restart-all succeeds', async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) })
    render(React.createElement(ServiceControls))
    fireEvent.click(screen.getByRole('button', { name: /restart all immich services/i }))
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /^restart all$/i }))
    })
    await waitFor(() => {
      expect(screen.getByRole('status')).toBeInTheDocument()
      expect(screen.getByRole('status')).toHaveTextContent('All services restarted.')
    })
  })

  it('shows error banner after restart-all fails', async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: false, json: async () => ({ detail: 'something went wrong' }) })
    render(React.createElement(ServiceControls))
    fireEvent.click(screen.getByRole('button', { name: /restart all immich services/i }))
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /^restart all$/i }))
    })
    await waitFor(() => {
      expect(screen.getByRole('status')).toBeInTheDocument()
      expect(screen.getByRole('status')).toHaveTextContent('Failed: something went wrong')
    })
  })

  it('shows error banner when restart-all throws a network error', async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error('Network error'))
    render(React.createElement(ServiceControls))
    fireEvent.click(screen.getByRole('button', { name: /restart all immich services/i }))
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /^restart all$/i }))
    })
    await waitFor(() => {
      expect(screen.getByRole('status')).toBeInTheDocument()
      expect(screen.getByRole('status')).toHaveTextContent('Failed to restart all services.')
    })
  })
})
