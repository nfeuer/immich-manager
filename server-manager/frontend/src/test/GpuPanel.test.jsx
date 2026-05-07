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
  name: 'NVIDIA RTX 3090',
  vendor: 'nvidia',
  temperature_c: 55,
  util_percent: 22,
  mem_util_percent: 18,
  mem_used_mb: 4096,
  mem_total_mb: 24576,
  power_draw_w: 178.5,
  power_limit_w: 350,
  pstate: 'P2',
  fan_speed_percent: 45,
  gfx_clock_mhz: 1500,
  pcie_gen: 3,
  pcie_width: 16,
  driver_version: '550.54.14',
}

const SAMPLE_HISTORY = {
  hours: 168,
  sample_interval_seconds: 10,
  gpu_metrics: [
    { ...SAMPLE_GPU, gpu_index: 0, timestamp: '2026-05-07 10:00:00' },
    { ...SAMPLE_GPU, gpu_index: 0, timestamp: '2026-05-07 10:05:00', temperature_c: 60 },
  ],
  system_power: [
    {
      timestamp: '2026-05-07 10:00:00',
      total_watts: 240,
      cpu_watts: 45,
      gpu_watts: 130,
      baseline_watts: 65,
      ac_watts: 261,
    },
    {
      timestamp: '2026-05-07 10:05:00',
      total_watts: 260,
      cpu_watts: 50,
      gpu_watts: 145,
      baseline_watts: 65,
      ac_watts: 283,
    },
  ],
}

const SAMPLE_SUMMARY = {
  day: {
    gpus: [
      {
        gpu_index: 0,
        gpu_name: 'NVIDIA RTX 3090',
        sample_count: 1440,
        idle_sample_count: 800,
        peak_temp: 70,
        peak_util: 90,
        peak_power: 320,
        avg_temp: 50,
        avg_power: 110,
        avg_util: 22,
        idle_temp: 42,
        idle_power: 30,
        power_limit: 350,
      },
    ],
    system_power: {
      sample_count: 1440,
      peak_watts: 480,
      avg_watts: 220,
      peak_ac_watts: 522,
      avg_ac_watts: 239,
      source: 'estimated',
    },
  },
  week: {
    gpus: [
      {
        gpu_index: 0,
        gpu_name: 'NVIDIA RTX 3090',
        sample_count: 10080,
        idle_sample_count: 5500,
        peak_temp: 75,
        peak_util: 95,
        peak_power: 340,
        avg_temp: 52,
        avg_power: 115,
        avg_util: 24,
        idle_temp: 41,
        idle_power: 28,
        power_limit: 350,
      },
    ],
    system_power: {
      sample_count: 10080,
      peak_watts: 510,
      avg_watts: 225,
      peak_ac_watts: 554,
      avg_ac_watts: 244,
      source: 'estimated',
    },
  },
  psu_watts: 750,
}

const SAMPLE_CURRENT = {
  available: true,
  vendor: 'nvidia',
  gpus: [SAMPLE_GPU],
  system_power: {
    total_watts: 240,
    ac_watts: 261,
    cpu_watts: 45,
    gpu_watts: 178.5,
    baseline_watts: 65,
    psu_efficiency: 0.92,
    source: 'estimated',
  },
  psu_watts: 750,
  psu_percent: 32,
  thresholds: {
    gpu_temp_warning: 80,
    gpu_temp_critical: 90,
    psu_warning_percent: 80,
    psu_critical_percent: 95,
  },
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
        thresholds: {
          gpu_temp_warning: 80,
          gpu_temp_critical: 90,
          psu_warning_percent: 80,
          psu_critical_percent: 95,
        },
      },
      isLoading: false,
    })
    useGpuSummary.mockReturnValue({
      data: { day: { gpus: [], system_power: {} }, week: { gpus: [], system_power: {} }, psu_watts: 0 },
      isLoading: false,
    })
    useGpuHistory.mockReturnValue({
      data: { gpu_metrics: [], system_power: [], sample_interval_seconds: 10 },
      isLoading: false,
    })
    render(React.createElement(GpuPanel), { wrapper })
    expect(screen.getByText(/No GPU detected/)).toBeInTheDocument()
  })

  it('renders GPU detail tiles, hardware metadata, and system power breakdown', () => {
    useGpuCurrent.mockReturnValue({ data: SAMPLE_CURRENT, isLoading: false })
    useGpuSummary.mockReturnValue({ data: SAMPLE_SUMMARY, isLoading: false })
    useGpuHistory.mockReturnValue({ data: SAMPLE_HISTORY, isLoading: false })

    render(React.createElement(GpuPanel), { wrapper })

    // Section headings
    expect(screen.getAllByText(/GPUs/).length).toBeGreaterThan(0)
    expect(screen.getByText(/System Power/)).toBeInTheDocument()
    // GPU name (in card header + chart legend)
    expect(screen.getAllByText(/NVIDIA RTX 3090/).length).toBeGreaterThan(0)
    // Hardware-detail badges
    expect(screen.getByText(/P2/)).toBeInTheDocument()
    expect(screen.getByText(/PCIe 3x16/)).toBeInTheDocument()
    expect(screen.getByText(/1500 MHz/)).toBeInTheDocument()
    // Idle stats appear (peak vs idle distinction)
    expect(screen.getByText(/Day Idle Power/)).toBeInTheDocument()
    expect(screen.getByText(/Day Peak Power/)).toBeInTheDocument()
    // Idle sample count surfaced so we know if idle data is meaningful
    expect(screen.getByText(/800 idle samples/)).toBeInTheDocument()
    // System power tiles include both DC and AC
    expect(screen.getByText('Now Total (DC)')).toBeInTheDocument()
    expect(screen.getByText('Now Total (AC)')).toBeInTheDocument()
    // PSU subtitle / metadata appears (in subtitle and Now Total tile)
    expect(screen.getAllByText(/750W PSU/).length).toBeGreaterThan(0)
  })

  it('shows per-GPU filter chips when more than one GPU is present', () => {
    const TWO_GPUS = {
      ...SAMPLE_CURRENT,
      gpus: [
        SAMPLE_GPU,
        { ...SAMPLE_GPU, index: 1, name: 'GTX 1080', power_limit_w: 180 },
      ],
    }
    useGpuCurrent.mockReturnValue({ data: TWO_GPUS, isLoading: false })
    useGpuSummary.mockReturnValue({ data: SAMPLE_SUMMARY, isLoading: false })
    useGpuHistory.mockReturnValue({ data: SAMPLE_HISTORY, isLoading: false })
    render(React.createElement(GpuPanel), { wrapper })
    expect(screen.getByRole('button', { name: 'GPU 0' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'GPU 1' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'All' })).toBeInTheDocument()
  })
})
