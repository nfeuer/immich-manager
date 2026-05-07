import { describe, it, expect, vi } from 'vitest'
import React from 'react'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import GpuPanel from '../components/GpuPanel.jsx'

vi.mock('../hooks/useDashboard.js', () => ({
  useGpuCurrent: vi.fn(),
  useGpuSummary: vi.fn(),
  useGpuHistory: vi.fn(),
}))

import {
  useGpuCurrent,
  useGpuSummary,
  useGpuHistory,
} from '../hooks/useDashboard.js'

function wrapper({ children }) {
  return React.createElement(
    QueryClientProvider,
    { client: new QueryClient() },
    children,
  )
}

const SAMPLE_GPU = {
  index: 0,
  uuid: 'GPU-A',
  name: 'NVIDIA RTX 3060',
  vendor: 'nvidia',
  temperature_c: 55,
  util_percent: 22,
  mem_util_percent: 18,
  mem_used_mb: 4096,
  mem_total_mb: 12288,
  power_draw_w: 78.5,
  power_limit_w: 170,
}

const SAMPLE_HISTORY = {
  hours: 168,
  gpu_metrics: [
    { ...SAMPLE_GPU, gpu_index: 0, timestamp: '2026-05-07 10:00:00' },
    { ...SAMPLE_GPU, gpu_index: 0, timestamp: '2026-05-07 10:05:00', temperature_c: 60 },
  ],
  system_power: [
    { timestamp: '2026-05-07 10:00:00', total_watts: 200 },
    { timestamp: '2026-05-07 10:05:00', total_watts: 220 },
  ],
}

const SAMPLE_SUMMARY = {
  day: {
    gpus: [
      {
        gpu_index: 0,
        gpu_name: 'NVIDIA RTX 3060',
        temp_max: 70,
        temp_min: 45,
        temp_avg: 55,
        util_max: 90,
        util_min: 0,
        util_avg: 22,
        power_max: 160,
        power_min: 12,
        power_avg: 60,
        power_limit: 170,
      },
    ],
    system_power: { total_max: 280, total_min: 150, total_avg: 210, source: 'estimated' },
  },
  week: {
    gpus: [
      {
        gpu_index: 0,
        gpu_name: 'NVIDIA RTX 3060',
        temp_max: 75,
        temp_min: 40,
        temp_avg: 56,
        util_max: 95,
        util_min: 0,
        util_avg: 24,
        power_max: 165,
        power_min: 10,
        power_avg: 62,
        power_limit: 170,
      },
    ],
    system_power: { total_max: 295, total_min: 145, total_avg: 215, source: 'estimated' },
  },
  psu_watts: 750,
}

describe('GpuPanel', () => {
  it('renders skeleton while all queries are loading', () => {
    useGpuCurrent.mockReturnValue({ data: undefined, isLoading: true })
    useGpuSummary.mockReturnValue({ data: undefined, isLoading: true })
    useGpuHistory.mockReturnValue({ data: undefined, isLoading: true })
    const { container } = render(React.createElement(GpuPanel), { wrapper })
    expect(container.querySelector('.animate-pulse')).toBeInTheDocument()
  })

  it('renders the no-GPU notice when monitor is unavailable', () => {
    useGpuCurrent.mockReturnValue({
      data: {
        available: false,
        vendor: null,
        gpus: [],
        system_power: { total_watts: null, source: 'unavailable' },
        psu_watts: 0,
        psu_percent: null,
      },
      isLoading: false,
    })
    useGpuSummary.mockReturnValue({
      data: { day: { gpus: [], system_power: {} }, week: { gpus: [], system_power: {} }, psu_watts: 0 },
      isLoading: false,
    })
    useGpuHistory.mockReturnValue({
      data: { gpu_metrics: [], system_power: [] },
      isLoading: false,
    })
    render(React.createElement(GpuPanel), { wrapper })
    expect(screen.getByText(/No GPU detected/)).toBeInTheDocument()
  })

  it('renders GPU stats and current power when data is available', () => {
    useGpuCurrent.mockReturnValue({
      data: {
        available: true,
        vendor: 'nvidia',
        gpus: [SAMPLE_GPU],
        system_power: {
          total_watts: 220,
          cpu_watts: 45,
          gpu_watts: 78.5,
          baseline_watts: 65,
          source: 'estimated',
        },
        psu_watts: 750,
        psu_percent: 29.3,
      },
      isLoading: false,
    })
    useGpuSummary.mockReturnValue({ data: SAMPLE_SUMMARY, isLoading: false })
    useGpuHistory.mockReturnValue({ data: SAMPLE_HISTORY, isLoading: false })

    render(React.createElement(GpuPanel), { wrapper })
    // Section headings
    expect(screen.getAllByText(/GPUs/).length).toBeGreaterThan(0)
    expect(screen.getByText(/System Power/)).toBeInTheDocument()
    // GPU name (renders once in card header, once in chart legend)
    expect(screen.getAllByText(/NVIDIA RTX 3060/).length).toBeGreaterThan(0)
    // Current temp shown
    expect(screen.getByText('55°C')).toBeInTheDocument()
    // Power draw with unit (appears in both Now Power and gpu_watts cells)
    expect(screen.getAllByText('78.5 W').length).toBeGreaterThan(0)
    // System power total
    expect(screen.getByText('220 W')).toBeInTheDocument()
    // PSU note rendered with PSU watts
    expect(screen.getByText(/750W PSU rail/)).toBeInTheDocument()
  })
})
