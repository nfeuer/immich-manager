import { describe, it, expect, vi, beforeEach } from 'vitest'
import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import LogViewer from '../components/LogViewer.jsx'

beforeEach(() => {
  global.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({
      lines: [
        { level: 'info', text: 'log line 1' },
        { level: 'warn', text: 'log line 2' },
        { level: 'error', text: 'log line 3' },
      ],
    }),
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

  it('renders log lines with text content', async () => {
    render(React.createElement(LogViewer))
    await waitFor(() => {
      expect(screen.getByText('log line 1')).toBeInTheDocument()
      expect(screen.getByText('log line 2')).toBeInTheDocument()
      expect(screen.getByText('log line 3')).toBeInTheDocument()
    })
  })

  it('renders All filter button as active by default', () => {
    render(React.createElement(LogViewer))
    const allBtn = screen.getByRole('button', { name: /^All$/ })
    expect(allBtn.className).toMatch(/border-immich-primary/)
  })

  it('clicking a level filter hides non-matching lines', async () => {
    render(React.createElement(LogViewer))
    await waitFor(() => screen.getByText('log line 1'))

    fireEvent.click(screen.getByRole('button', { name: /^Error$/ }))

    expect(screen.queryByText('log line 1')).not.toBeInTheDocument() // info
    expect(screen.queryByText('log line 2')).not.toBeInTheDocument() // warn
    expect(screen.getByText('log line 3')).toBeInTheDocument()       // error
  })

  it('clicking All resets filter and shows all lines', async () => {
    render(React.createElement(LogViewer))
    await waitFor(() => screen.getByText('log line 1'))

    fireEvent.click(screen.getByRole('button', { name: /^Error$/ }))
    fireEvent.click(screen.getByRole('button', { name: /^All$/ }))

    expect(screen.getByText('log line 1')).toBeInTheDocument()
    expect(screen.getByText('log line 2')).toBeInTheDocument()
    expect(screen.getByText('log line 3')).toBeInTheDocument()
  })

  it('shows filtered line count when a filter is active', async () => {
    render(React.createElement(LogViewer))
    await waitFor(() => screen.getByText('log line 1'))

    fireEvent.click(screen.getByRole('button', { name: /^Error$/ }))

    expect(screen.getByText(/1 of 3 lines/)).toBeInTheDocument()
  })

  it('shows total line count with no filter active', async () => {
    render(React.createElement(LogViewer))
    await waitFor(() => screen.getByText(/3 lines/))
    expect(screen.getByText('3 lines')).toBeInTheDocument()
  })

  it('shows empty filter message when no lines match', async () => {
    render(React.createElement(LogViewer))
    await waitFor(() => screen.getByText('log line 1'))

    fireEvent.click(screen.getByRole('button', { name: /^Debug$/ }))

    expect(screen.getByText(/No lines match the active filter/)).toBeInTheDocument()
  })
})
