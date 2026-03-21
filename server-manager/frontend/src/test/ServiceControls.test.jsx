import { describe, it, expect, vi, beforeEach } from 'vitest'
import React from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import ServiceControls from '../components/ServiceControls.jsx'

beforeEach(() => {
  global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) })
  global.confirm = vi.fn().mockReturnValue(true)
  global.alert = vi.fn()
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

  it('calls POST /api/services/{service}/restart when a restart button is clicked', async () => {
    render(React.createElement(ServiceControls))
    const buttons = screen.getAllByRole('button', { name: /restart/i })
    // First button corresponds to immich_server (the first service)
    fireEvent.click(buttons[0])
    expect(global.confirm).toHaveBeenCalledWith('Restart immich_server?')
    expect(global.fetch).toHaveBeenCalledWith(
      '/api/services/immich_server/restart',
      { method: 'POST' }
    )
  })

  it('calls POST /api/services/restart-all when "Restart All Immich Services" is clicked', async () => {
    render(React.createElement(ServiceControls))
    const restartAllBtn = screen.getByRole('button', { name: /restart all immich services/i })
    fireEvent.click(restartAllBtn)
    expect(global.confirm).toHaveBeenCalledWith(
      'Restart ALL Immich services? This will briefly interrupt Immich.'
    )
    expect(global.fetch).toHaveBeenCalledWith('/api/services/restart-all', { method: 'POST' })
  })
})
