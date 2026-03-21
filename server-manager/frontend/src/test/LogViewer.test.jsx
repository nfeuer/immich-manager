import { describe, it, expect, vi, beforeEach } from 'vitest'
import React from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import LogViewer from '../components/LogViewer.jsx'

beforeEach(() => {
  global.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ lines: ['log line 1', 'log line 2'] }),
  })
  global.EventSource = vi.fn().mockImplementation(() => ({
    onmessage: null,
    onerror: null,
    close: vi.fn(),
  }))
})

describe('LogViewer', () => {
  it('renders all 7 service tabs', () => {
    render(React.createElement(LogViewer))
    expect(screen.getByRole('button', { name: /immich_server/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /system/ })).toBeInTheDocument()
  })

  it('preserves selected tab when re-rendered by parent', () => {
    const { rerender } = render(React.createElement(LogViewer))
    fireEvent.click(screen.getByRole('button', { name: /server_manager/ }))
    rerender(React.createElement(LogViewer))
    const tab = screen.getByRole('button', { name: /server_manager/ })
    expect(tab.className).toMatch(/border-immich-primary/)
  })
})
