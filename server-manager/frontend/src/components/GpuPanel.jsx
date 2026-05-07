import { useMemo, useState } from 'react'
import {
  CpuChipIcon,
  BoltIcon,
  FireIcon,
  ChartBarIcon,
  CircleStackIcon,
  ExclamationTriangleIcon,
  InformationCircleIcon,
} from '@heroicons/react/24/outline'
import {
  useGpuCurrent,
  useGpuSummary,
  useGpuHistory,
  useBaselineCalibration,
} from '../hooks/useDashboard.js'
import LineChart from './LineChart.jsx'
import Skeleton from './Skeleton.jsx'

// Stable color palette — GPU 0 stays blue across all charts.
const GPU_COLORS = ['#60a5fa', '#f472b6', '#4ade80', '#facc15']
const STACK_COLORS = {
  cpu: '#a78bfa',
  gpu0: '#60a5fa',
  gpu1: '#f472b6',
  gpu2: '#4ade80',
  baseline: '#475569',
}

function fmtNum(v, suffix = '', digits = 0) {
  if (v == null || !isFinite(v)) return '—'
  return `${Number(v).toFixed(digits)}${suffix}`
}

function tempTone(temp, warning, critical) {
  if (temp == null) return 'default'
  if (temp >= critical) return 'critical'
  if (temp >= warning) return 'warning'
  return 'success'
}

function powerTone(pct) {
  if (pct == null) return 'default'
  if (pct >= 95) return 'critical'
  if (pct >= 80) return 'warning'
  return 'default'
}

function StatTile({ label, value, sub, tone = 'default', help }) {
  const toneClass =
    tone === 'critical'
      ? 'text-immich-error'
      : tone === 'warning'
      ? 'text-immich-warning'
      : tone === 'success'
      ? 'text-immich-success'
      : 'text-immich-text'
  return (
    <div className="bg-immich-bg/60 border border-immich-border rounded-lg px-3 py-2" title={help}>
      <div className="flex items-center justify-between gap-1 mb-0.5">
        <span className="text-[10px] uppercase tracking-wider text-immich-muted">{label}</span>
        {help && <InformationCircleIcon className="w-3 h-3 text-immich-muted/60" />}
      </div>
      <div className={`text-base font-semibold font-mono ${toneClass}`}>{value}</div>
      {sub && <div className="text-[10px] text-immich-muted mt-0.5 font-mono leading-tight">{sub}</div>}
    </div>
  )
}

function MeterRow({ label, value, max, suffix = '', tone = 'default' }) {
  const pct = value != null && max ? Math.min(100, (value / max) * 100) : 0
  const fillClass =
    tone === 'critical'
      ? 'bg-immich-error'
      : tone === 'warning'
      ? 'bg-immich-warning'
      : 'bg-immich-info'
  return (
    <div>
      <div className="flex items-center justify-between text-xs mb-1">
        <span className="text-immich-muted">{label}</span>
        <span className="text-immich-text font-mono">
          {fmtNum(value, suffix, suffix === ' W' ? 1 : 0)}
          {max ? <span className="text-immich-muted"> / {fmtNum(max, suffix)}</span> : null}
        </span>
      </div>
      <div className="h-1.5 bg-immich-border rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ${fillClass}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

function GpuCard({ gpu, daySummary, weekSummary, thresholds }) {
  const tdpPct =
    gpu.power_draw_w != null && gpu.power_limit_w
      ? (gpu.power_draw_w / gpu.power_limit_w) * 100
      : null
  return (
    <div className="border border-immich-border rounded-xl p-4">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
        <div>
          <div className="text-[10px] text-immich-muted uppercase tracking-wider">
            GPU {gpu.index} · {gpu.vendor}
            {gpu.driver_version ? ` · driver ${gpu.driver_version}` : ''}
          </div>
          <div className="text-sm font-semibold text-immich-text">{gpu.name}</div>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-[11px] font-mono">
          {gpu.pstate && (
            <span
              className={`px-1.5 py-0.5 rounded border ${
                gpu.pstate === 'P0'
                  ? 'border-immich-warning text-immich-warning'
                  : 'border-immich-border text-immich-muted'
              }`}
              title="P-state: P0 = max performance, P8 = idle"
            >
              {gpu.pstate}
            </span>
          )}
          {gpu.fan_speed_percent != null && (
            <span className="px-1.5 py-0.5 rounded border border-immich-border text-immich-muted">
              fan {fmtNum(gpu.fan_speed_percent, '%')}
            </span>
          )}
          {gpu.gfx_clock_mhz && (
            <span className="px-1.5 py-0.5 rounded border border-immich-border text-immich-muted">
              {fmtNum(gpu.gfx_clock_mhz, ' MHz')}
            </span>
          )}
          {gpu.pcie_gen && gpu.pcie_width && (
            <span className="px-1.5 py-0.5 rounded border border-immich-border text-immich-muted">
              PCIe {fmtNum(gpu.pcie_gen)}x{fmtNum(gpu.pcie_width)}
            </span>
          )}
        </div>
      </div>

      <div className="grid md:grid-cols-2 gap-4 mb-4">
        <div className="space-y-3">
          <MeterRow
            label="Temperature"
            value={gpu.temperature_c}
            max={Math.max(thresholds.gpu_temp_critical + 10, 100)}
            suffix="°C"
            tone={tempTone(gpu.temperature_c, thresholds.gpu_temp_warning, thresholds.gpu_temp_critical)}
          />
          <MeterRow
            label="GPU Utilization"
            value={gpu.util_percent}
            max={100}
            suffix="%"
          />
          <MeterRow
            label="Power"
            value={gpu.power_draw_w}
            max={gpu.power_limit_w}
            suffix=" W"
            tone={powerTone(tdpPct)}
          />
          {gpu.mem_total_mb && (
            <MeterRow
              label="VRAM"
              value={gpu.mem_used_mb}
              max={gpu.mem_total_mb}
              suffix=" MB"
            />
          )}
        </div>

        <div className="grid grid-cols-3 gap-2">
          <StatTile
            label="Day Peak Temp"
            value={fmtNum(daySummary?.peak_temp, '°C')}
            sub={`avg ${fmtNum(daySummary?.avg_temp, '°C')}`}
          />
          <StatTile
            label="Day Idle Temp"
            value={fmtNum(daySummary?.idle_temp, '°C')}
            sub={`${fmtNum(daySummary?.idle_sample_count, '')} idle samples`}
            help="Average temperature on samples where GPU utilization was under 5%"
          />
          <StatTile
            label="Day Peak Power"
            value={fmtNum(daySummary?.peak_power, ' W', 0)}
            sub={`limit ${fmtNum(gpu.power_limit_w, ' W')}`}
          />
          <StatTile
            label="Day Idle Power"
            value={fmtNum(daySummary?.idle_power, ' W', 1)}
            sub={`avg ${fmtNum(daySummary?.avg_power, ' W')}`}
            help="Average power on samples where GPU utilization was under 5%"
          />
          <StatTile
            label="Week Peak Temp"
            value={fmtNum(weekSummary?.peak_temp, '°C')}
            sub={`avg ${fmtNum(weekSummary?.avg_temp, '°C')}`}
          />
          <StatTile
            label="Week Peak Power"
            value={fmtNum(weekSummary?.peak_power, ' W', 0)}
            sub={`avg ${fmtNum(weekSummary?.avg_power, ' W')}`}
          />
        </div>
      </div>
    </div>
  )
}

function buildSeriesByGpu(history, field, gpuFilter) {
  if (!history) return []
  const byIdx = new Map()
  for (const row of history) {
    const idx = row.gpu_index
    if (gpuFilter != null && idx !== gpuFilter) continue
    if (!byIdx.has(idx)) byIdx.set(idx, { name: `GPU ${idx}`, points: [] })
    const v = row[field]
    byIdx.get(idx).points.push({
      // SQLite CURRENT_TIMESTAMP is UTC without a 'Z' — append it so JS parses correctly.
      t: new Date(row.timestamp.replace(' ', 'T') + 'Z').getTime(),
      v: v == null ? null : Number(v),
    })
  }
  return [...byIdx.entries()]
    .sort(([a], [b]) => a - b)
    .map(([idx, s]) => ({
      ...s,
      name: `GPU ${idx}`,
      color: GPU_COLORS[idx % GPU_COLORS.length],
    }))
}

function buildDiskIoSeries(diskHistory) {
  // One total throughput point per timestamp (read + write across devices),
  // aggregated to make correlation against the power chart obvious.
  // Per-device breakdown is shown as separate light series so a single
  // hammered drive is identifiable.
  if (!diskHistory) return []
  const byDevice = new Map()
  for (const r of diskHistory) {
    const t = new Date(r.timestamp.replace(' ', 'T') + 'Z').getTime()
    const dev = r.device
    if (!byDevice.has(dev)) byDevice.set(dev, [])
    const total = (Number(r.read_mb_s) || 0) + (Number(r.write_mb_s) || 0)
    byDevice.get(dev).push({ t, v: total })
  }
  const colors = ['#60a5fa', '#f472b6', '#4ade80', '#facc15', '#a78bfa', '#fb923c']
  return [...byDevice.entries()].map(([dev, points], i) => ({
    name: dev,
    color: colors[i % colors.length],
    points,
  }))
}

function buildSystemPowerStack(systemHistory, gpuHistory) {
  // Build CPU / per-GPU / baseline series for stacked area chart.
  // Use system_power for cpu_watts and baseline; sum gpu_metrics by index
  // joined on the closest preceding system_power timestamp bucket.
  if (!systemHistory) return []

  const sysPoints = systemHistory.map((r) => ({
    t: new Date(r.timestamp.replace(' ', 'T') + 'Z').getTime(),
    cpu: r.cpu_watts,
    baseline: r.baseline_watts ?? 0,
  }))

  // Bucket GPU samples by their nearest system_power timestamp (60s buckets are
  // fine because both are sampled in the same job — timestamps are nearly equal).
  const gpuByBucket = new Map() // bucket-ms -> Map(idx -> watts)
  if (gpuHistory) {
    for (const r of gpuHistory) {
      const t = new Date(r.timestamp.replace(' ', 'T') + 'Z').getTime()
      const bucket = Math.round(t / 5000) * 5000
      if (!gpuByBucket.has(bucket)) gpuByBucket.set(bucket, new Map())
      gpuByBucket.get(bucket).set(r.gpu_index, r.power_draw_w)
    }
  }

  const allGpuIdxs = new Set()
  for (const m of gpuByBucket.values()) for (const i of m.keys()) allGpuIdxs.add(i)
  const sortedGpuIdxs = [...allGpuIdxs].sort((a, b) => a - b)

  const cpuSeries = { name: 'CPU', color: STACK_COLORS.cpu, points: [] }
  const baselineSeries = { name: 'Other (mobo+drives)', color: STACK_COLORS.baseline, points: [] }
  const gpuSeries = sortedGpuIdxs.map((idx) => ({
    name: `GPU ${idx}`,
    color: STACK_COLORS[`gpu${idx}`] ?? GPU_COLORS[idx % GPU_COLORS.length],
    points: [],
    _idx: idx,
  }))

  for (const sp of sysPoints) {
    const bucket = Math.round(sp.t / 5000) * 5000
    const gpuMap = gpuByBucket.get(bucket)
    cpuSeries.points.push({ t: sp.t, v: sp.cpu })
    baselineSeries.points.push({ t: sp.t, v: sp.baseline })
    for (const s of gpuSeries) {
      const v = gpuMap?.get(s._idx)
      s.points.push({ t: sp.t, v: v == null ? 0 : v })
    }
  }

  return [cpuSeries, ...gpuSeries, baselineSeries]
}

function SystemPowerStats({ current, daySummary, weekSummary, psuWatts }) {
  const dcNow = current?.total_watts
  const acNow = current?.ac_watts
  const dcPct = dcNow != null && psuWatts ? (dcNow / psuWatts) * 100 : null
  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2">
      <StatTile
        label="Now Total (DC)"
        value={fmtNum(dcNow, ' W', 0)}
        sub={
          psuWatts && dcPct != null
            ? `${fmtNum(dcPct, '%', 0)} of ${psuWatts}W PSU`
            : current?.source
            ? `via ${current.source}`
            : null
        }
        tone={powerTone(dcPct)}
        help="DC component sum: CPU + GPUs + baseline. This is what your PSU has to supply on its rails."
      />
      <StatTile
        label="Now Total (AC)"
        value={fmtNum(acNow, ' W', 0)}
        sub={current?.psu_efficiency ? `at ${fmtNum(current.psu_efficiency * 100, '%')} eff.` : null}
        help="Estimated wall-power draw. Higher than DC because PSUs aren't 100% efficient."
      />
      <StatTile label="CPU" value={fmtNum(current?.cpu_watts, ' W', 1)} />
      <StatTile label="All GPUs" value={fmtNum(current?.gpu_watts, ' W', 1)} />
      <StatTile
        label="Day Peak"
        value={fmtNum(daySummary?.peak_watts, ' W', 0)}
        sub={`avg ${fmtNum(daySummary?.avg_watts, ' W')}`}
      />
      <StatTile
        label="Week Peak"
        value={fmtNum(weekSummary?.peak_watts, ' W', 0)}
        sub={`avg ${fmtNum(weekSummary?.avg_watts, ' W')}`}
      />
    </div>
  )
}

const RANGES = [
  { label: '1h', hours: 1 },
  { label: '24h', hours: 24 },
  { label: '3d', hours: 72 },
  { label: '7d', hours: 168 },
]

function ChipGroup({ value, options, onChange }) {
  return (
    <div className="inline-flex bg-immich-bg border border-immich-border rounded-lg p-0.5">
      {options.map((opt) => (
        <button
          key={opt.value}
          type="button"
          onClick={() => onChange(opt.value)}
          className={`px-2.5 py-1 text-xs font-medium rounded-md transition-colors ${
            value === opt.value
              ? 'bg-immich-primary text-white'
              : 'text-immich-muted hover:text-immich-text'
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  )
}

function Section({ title, icon: Icon, children, action, subtitle }) {
  return (
    <div className="bg-immich-surface border border-immich-border rounded-2xl p-5 mb-6">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
        <div>
          <h2 className="flex items-center gap-2 text-sm font-semibold text-immich-text">
            <Icon className="w-4 h-4 text-immich-muted" />
            {title}
          </h2>
          {subtitle && <p className="text-[11px] text-immich-muted mt-0.5">{subtitle}</p>}
        </div>
        {action}
      </div>
      {children}
    </div>
  )
}

function BaselineCalibration({ baselineWatts }) {
  const [requested, setRequested] = useState(false)
  const { data, isLoading, refetch } = useBaselineCalibration(requested)

  const onClick = () => {
    if (!requested) setRequested(true)
    else refetch()
  }

  return (
    <div className="mt-3 p-3 border border-immich-border rounded-lg">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-1">
        <div className="text-xs font-semibold text-immich-text">
          Baseline calibration
          <span className="ml-2 text-immich-muted font-normal font-mono">
            current: {baselineWatts != null ? `${baselineWatts}W` : '—'}
          </span>
        </div>
        <button
          type="button"
          onClick={onClick}
          className="px-3 py-1 text-xs font-medium rounded-md bg-immich-primary text-white hover:bg-immich-primary-hover disabled:opacity-50"
          disabled={isLoading}
        >
          {isLoading ? 'Computing…' : requested ? 'Recompute' : 'Recommend'}
        </button>
      </div>
      <p className="text-[11px] text-immich-muted">
        Averages <code className="font-mono">total − cpu − gpu</code> over the last 24 h of
        samples where every GPU was below 5% util. The result is your real motherboard +
        drives + fans wattage. Run after a quiet period (overnight is ideal).
      </p>
      {data && (
        <div className="mt-2 text-xs grid grid-cols-2 sm:grid-cols-4 gap-2 font-mono">
          <div>
            <span className="text-immich-muted">samples</span>{' '}
            <span className="text-immich-text">{data.sample_count}</span>
          </div>
          <div>
            <span className="text-immich-muted">min</span>{' '}
            <span className="text-immich-text">{fmtNum(data.min_residual, 'W', 1)}</span>
          </div>
          <div>
            <span className="text-immich-muted">median</span>{' '}
            <span className="text-immich-success">
              {fmtNum(data.median_residual, 'W', 1)}
            </span>
          </div>
          <div>
            <span className="text-immich-muted">max</span>{' '}
            <span className="text-immich-text">{fmtNum(data.max_residual, 'W', 1)}</span>
          </div>
          {data.recommended_baseline_watts != null && (
            <div className="col-span-full text-[11px] text-immich-muted mt-1">
              Suggested:{' '}
              <code className="font-mono text-immich-text">
                system_power_baseline_watts: {data.recommended_baseline_watts}
              </code>
              {baselineWatts != null && (
                <>
                  {' '}
                  (currently {baselineWatts}W,{' '}
                  {Math.abs(data.recommended_baseline_watts - baselineWatts) < 5
                    ? 'close enough — no change needed'
                    : 'consider updating config.yaml'}
                  )
                </>
              )}
            </div>
          )}
          {data.sample_count === 0 && (
            <div className="col-span-full text-[11px] text-immich-warning mt-1">
              No idle samples found yet. Need at least one moment where every GPU was
              under 5% util in the last 24 h.
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function GpuPanel() {
  const [hours, setHours] = useState(168)
  const [gpuFilter, setGpuFilter] = useState('all')
  const { data: current, isLoading: loadingCurrent } = useGpuCurrent()
  const { data: summary, isLoading: loadingSummary } = useGpuSummary()
  const { data: history, isLoading: loadingHistory } = useGpuHistory(hours)

  const thresholds = current?.thresholds ?? {
    gpu_temp_warning: 80,
    gpu_temp_critical: 90,
    psu_warning_percent: 80,
    psu_critical_percent: 95,
  }

  const filterIdx = gpuFilter === 'all' ? null : Number(gpuFilter)
  const tempSeries = useMemo(
    () => buildSeriesByGpu(history?.gpu_metrics, 'temperature_c', filterIdx),
    [history, filterIdx],
  )
  const utilSeries = useMemo(
    () => buildSeriesByGpu(history?.gpu_metrics, 'util_percent', filterIdx),
    [history, filterIdx],
  )
  const powerSeriesGpu = useMemo(
    () => buildSeriesByGpu(history?.gpu_metrics, 'power_draw_w', filterIdx),
    [history, filterIdx],
  )
  const stackedPowerSeries = useMemo(
    () => buildSystemPowerStack(history?.system_power, history?.gpu_metrics),
    [history],
  )
  const diskIoSeries = useMemo(
    () => buildDiskIoSeries(history?.disk_io),
    [history],
  )

  const gpuSummaryByIdx = (bucket) => {
    const out = new Map()
    for (const g of bucket?.gpus ?? []) out.set(g.gpu_index, g)
    return out
  }
  const daySummary = useMemo(() => gpuSummaryByIdx(summary?.day), [summary])
  const weekSummary = useMemo(() => gpuSummaryByIdx(summary?.week), [summary])

  const gpus = current?.gpus ?? []
  const psuWatts = current?.psu_watts ?? summary?.psu_watts ?? 0
  const sampleInterval = history?.sample_interval_seconds ?? 60
  // Break gaps after 3× the expected sample interval so a missed sample doesn't
  // create a fake hole, but real downtime does.
  const gapMinutes = Math.max(1, Math.round((sampleInterval * 3) / 60))

  if (loadingCurrent && loadingSummary && loadingHistory) {
    return (
      <Section title="GPUs & Power" icon={CpuChipIcon}>
        <Skeleton height="6rem" width="100%" className="mb-3" />
        <Skeleton height="11rem" width="100%" />
      </Section>
    )
  }

  if (!loadingCurrent && current && !current.available) {
    return (
      <Section title="GPUs & Power" icon={CpuChipIcon}>
        <div className="text-sm text-immich-muted flex items-start gap-2">
          <ExclamationTriangleIcon className="w-4 h-4 text-immich-warning flex-shrink-0 mt-0.5" />
          <div>
            No GPU detected. Install <code className="font-mono text-immich-text">nvidia-smi</code> (NVIDIA)
            or <code className="font-mono text-immich-text">rocm-smi</code> (AMD) and ensure they're on the
            server-manager service's PATH. System power continues to be sampled when available.
          </div>
        </div>
        <div className="mt-4">
          <SystemPowerStats
            current={current?.system_power}
            daySummary={summary?.day?.system_power}
            weekSummary={summary?.week?.system_power}
            psuWatts={psuWatts}
          />
        </div>
      </Section>
    )
  }

  const psuWarningLine = psuWatts ? psuWatts * (thresholds.psu_warning_percent / 100) : null
  const psuCriticalLine = psuWatts ? psuWatts * (thresholds.psu_critical_percent / 100) : null

  // GPU filter chips list — built from sample data so it survives offline GPUs.
  const gpuFilterOptions = [
    { value: 'all', label: 'All' },
    ...gpus.map((g) => ({ value: String(g.index), label: `GPU ${g.index}` })),
  ]

  return (
    <>
      <Section
        title="GPUs"
        icon={CpuChipIcon}
        subtitle={
          gpus.length > 0
            ? `${gpus.length} ${gpus.length === 1 ? 'GPU' : 'GPUs'} sampled every ${sampleInterval}s · ${
                current?.vendor ?? ''
              }`
            : 'Waiting for first sample…'
        }
        action={
          <div className="flex items-center gap-2">
            {gpus.length > 1 && (
              <ChipGroup value={gpuFilter} options={gpuFilterOptions} onChange={setGpuFilter} />
            )}
            <ChipGroup
              value={hours}
              options={RANGES.map((r) => ({ value: r.hours, label: r.label }))}
              onChange={setHours}
            />
          </div>
        }
      >
        {gpus.length > 0 && (
          <div className="space-y-4 mb-6">
            {gpus.map((gpu) => (
              <GpuCard
                key={gpu.uuid ?? gpu.index}
                gpu={gpu}
                daySummary={daySummary.get(gpu.index)}
                weekSummary={weekSummary.get(gpu.index)}
                thresholds={thresholds}
              />
            ))}
          </div>
        )}

        <div className="grid grid-cols-1 xl:grid-cols-3 gap-5">
          <div>
            <div className="flex items-center gap-1.5 text-xs text-immich-muted uppercase tracking-wider mb-2">
              <FireIcon className="w-3.5 h-3.5" />
              Temperature
            </div>
            <LineChart
              series={tempSeries}
              unit="°C"
              spanHours={hours}
              gapMinutes={gapMinutes}
              ariaLabel="GPU temperature over time"
              threshold={thresholds.gpu_temp_warning}
              thresholdLabel={`warn ${thresholds.gpu_temp_warning}°C`}
              yMin="auto"
            />
          </div>
          <div>
            <div className="flex items-center gap-1.5 text-xs text-immich-muted uppercase tracking-wider mb-2">
              <ChartBarIcon className="w-3.5 h-3.5" />
              Utilization
            </div>
            <LineChart
              series={utilSeries}
              unit="%"
              yMax={100}
              spanHours={hours}
              gapMinutes={gapMinutes}
              ariaLabel="GPU utilization over time"
            />
          </div>
          <div>
            <div className="flex items-center gap-1.5 text-xs text-immich-muted uppercase tracking-wider mb-2">
              <BoltIcon className="w-3.5 h-3.5" />
              GPU Power Draw
            </div>
            <LineChart
              series={powerSeriesGpu}
              unit=" W"
              spanHours={hours}
              gapMinutes={gapMinutes}
              ariaLabel="GPU power draw over time"
            />
          </div>
        </div>

        {gpus.length > 0 && (
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-4 text-xs text-immich-muted">
            {(filterIdx == null ? gpus : gpus.filter((g) => g.index === filterIdx)).map((gpu) => (
              <span key={gpu.uuid ?? gpu.index} className="inline-flex items-center gap-1.5">
                <span
                  className="inline-block w-3 h-0.5"
                  style={{ background: GPU_COLORS[gpu.index % GPU_COLORS.length] }}
                />
                GPU {gpu.index} {gpu.name}
              </span>
            ))}
          </div>
        )}
      </Section>

      <Section
        title="System Power"
        icon={BoltIcon}
        subtitle={
          current?.system_power?.source
            ? `source: ${current.system_power.source}${
                psuWatts ? ` · ${psuWatts}W PSU` : ''
              }${
                current.system_power.psu_efficiency
                  ? ` · ${(current.system_power.psu_efficiency * 100).toFixed(0)}% efficiency`
                  : ''
              }`
            : null
        }
      >
        <SystemPowerStats
          current={current?.system_power}
          daySummary={summary?.day?.system_power}
          weekSummary={summary?.week?.system_power}
          psuWatts={psuWatts}
        />
        <div className="mt-5">
          <LineChart
            series={stackedPowerSeries}
            unit=" W"
            spanHours={hours}
            gapMinutes={gapMinutes}
            ariaLabel="System power breakdown over time"
            threshold={psuCriticalLine}
            thresholdLabel={psuWatts ? `${thresholds.psu_critical_percent}% PSU` : null}
            stacked
          />
          {/* Legend */}
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-3 text-xs text-immich-muted">
            {stackedPowerSeries.map((s) => (
              <span key={s.name} className="inline-flex items-center gap-1.5">
                <span
                  className="inline-block w-3 h-2 rounded-sm"
                  style={{ background: s.color, opacity: 0.7 }}
                />
                {s.name}
              </span>
            ))}
            {psuWarningLine && (
              <span className="inline-flex items-center gap-1.5 ml-auto">
                <span className="inline-block w-3 h-0.5 bg-immich-warning" />
                PSU {thresholds.psu_critical_percent}% line ({fmtNum(psuCriticalLine, ' W')})
              </span>
            )}
          </div>
          <div className="mt-3 text-[11px] text-immich-muted space-y-1">
            {current?.system_power?.source === 'estimated' && (
              <p>
                DC components: CPU package (Intel RAPL) + GPUs (nvidia-smi) +{' '}
                {fmtNum(current?.system_power?.baseline_watts, ' W')} baseline. Estimated AC
                wall power = DC ÷ {fmtNum((current?.system_power?.psu_efficiency ?? 0.92) * 100, '%')}{' '}
                efficiency. Install <code className="font-mono">ipmitool</code> if your board has IPMI for
                exact AC readings.
              </p>
            )}
            {current?.system_power?.source === 'ipmi' && (
              <p>
                AC reading from <code className="font-mono">ipmitool dcmi power reading</code>; DC computed
                using {fmtNum((current?.system_power?.psu_efficiency ?? 0.92) * 100, '%')} PSU efficiency.
              </p>
            )}
            {current?.system_power?.source === 'hwmon' && (
              <p>
                AC reading from board sensor (<code className="font-mono">hwmon power1_input</code>); DC
                computed using {fmtNum((current?.system_power?.psu_efficiency ?? 0.92) * 100, '%')}{' '}
                efficiency.
              </p>
            )}
            {!psuWatts && (
              <p>
                Set <code className="font-mono">thresholds.psu_watts</code> in config to overlay your PSU
                rail on the chart and enable headroom alerts.
              </p>
            )}
          </div>
          <BaselineCalibration baselineWatts={current?.system_power?.baseline_watts} />
        </div>

        {diskIoSeries.length > 0 && (
          <div className="mt-6 pt-5 border-t border-immich-border">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-1.5 text-xs text-immich-muted uppercase tracking-wider">
                <CircleStackIcon className="w-3.5 h-3.5" />
                Disk Activity (read + write, MB/s per device)
              </div>
              <span className="text-[10px] text-immich-muted">
                aligned with power chart above — hover to compare timestamps
              </span>
            </div>
            <LineChart
              series={diskIoSeries}
              unit=" MB/s"
              spanHours={hours}
              gapMinutes={gapMinutes}
              ariaLabel="Disk IO throughput over time"
              yMin={0}
            />
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-2 text-xs text-immich-muted">
              {diskIoSeries.map((s) => (
                <span key={s.name} className="inline-flex items-center gap-1.5">
                  <span
                    className="inline-block w-3 h-0.5"
                    style={{ background: s.color }}
                  />
                  <span className="font-mono">{s.name}</span>
                </span>
              ))}
            </div>
          </div>
        )}
      </Section>
    </>
  )
}
