import { useMemo, useState } from 'react'
import {
  CpuChipIcon,
  BoltIcon,
  FireIcon,
  ChartBarIcon,
  ExclamationTriangleIcon,
} from '@heroicons/react/24/outline'
import {
  useGpuCurrent,
  useGpuSummary,
  useGpuHistory,
} from '../hooks/useDashboard.js'
import LineChart from './LineChart.jsx'
import Skeleton from './Skeleton.jsx'

// Per-GPU palette — keep deterministic so dual-GPU charts stay readable.
const GPU_COLORS = ['#60a5fa', '#f472b6', '#4ade80', '#facc15']

function fmtNum(v, suffix = '', digits = 0) {
  if (v == null || !isFinite(v)) return '—'
  return `${Number(v).toFixed(digits)}${suffix}`
}

function StatTile({ label, value, sub, tone = 'default' }) {
  const toneClass =
    tone === 'critical'
      ? 'text-immich-error'
      : tone === 'warning'
      ? 'text-immich-warning'
      : tone === 'success'
      ? 'text-immich-success'
      : 'text-immich-text'
  return (
    <div className="bg-immich-bg/60 border border-immich-border rounded-lg px-3 py-2">
      <div className="text-[10px] uppercase tracking-wider text-immich-muted mb-0.5">{label}</div>
      <div className={`text-base font-semibold font-mono ${toneClass}`}>{value}</div>
      {sub && <div className="text-[10px] text-immich-muted mt-0.5 font-mono">{sub}</div>}
    </div>
  )
}

function tempTone(temp, warning, critical) {
  if (temp == null) return 'default'
  if (temp >= critical) return 'critical'
  if (temp >= warning) return 'warning'
  return 'success'
}

function Section({ title, icon: Icon, children, action }) {
  return (
    <div className="bg-immich-surface border border-immich-border rounded-2xl p-5 mb-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-immich-text">
          <Icon className="w-4 h-4 text-immich-muted" />
          {title}
        </h2>
        {action}
      </div>
      {children}
    </div>
  )
}

function GpuStatGrid({ gpu, daySummary, weekSummary, gpuTempWarning = 80, gpuTempCritical = 90 }) {
  const limit = gpu?.power_limit_w
  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2">
      <StatTile
        label="Now Temp"
        value={fmtNum(gpu?.temperature_c, '°C')}
        tone={tempTone(gpu?.temperature_c, gpuTempWarning, gpuTempCritical)}
      />
      <StatTile
        label="Now Util"
        value={fmtNum(gpu?.util_percent, '%')}
      />
      <StatTile
        label="Now Power"
        value={fmtNum(gpu?.power_draw_w, ' W', 1)}
        sub={limit ? `limit ${fmtNum(limit, ' W')}` : null}
      />
      <StatTile
        label="Day High"
        value={fmtNum(daySummary?.temp_max, '°C')}
        sub={`${fmtNum(daySummary?.power_max, ' W')} · ${fmtNum(daySummary?.util_max, '%')}`}
      />
      <StatTile
        label="Day Idle"
        value={fmtNum(daySummary?.temp_min, '°C')}
        sub={`${fmtNum(daySummary?.power_min, ' W')} · ${fmtNum(daySummary?.util_min, '%')}`}
      />
      <StatTile
        label="Week High"
        value={fmtNum(weekSummary?.temp_max, '°C')}
        sub={`${fmtNum(weekSummary?.power_max, ' W')} · ${fmtNum(weekSummary?.util_max, '%')}`}
      />
    </div>
  )
}

function buildSeriesByGpu(history, field) {
  if (!history) return []
  const byIdx = new Map()
  for (const row of history) {
    const idx = row.gpu_index
    if (!byIdx.has(idx)) byIdx.set(idx, { name: `GPU ${idx}`, points: [] })
    const v = row[field]
    byIdx.get(idx).points.push({
      t: new Date(row.timestamp + 'Z').getTime(),
      v: v == null ? null : Number(v),
    })
  }
  return [...byIdx.entries()]
    .sort(([a], [b]) => a - b)
    .map(([idx, s], i) => ({
      ...s,
      name: `GPU ${idx}`,
      color: GPU_COLORS[i % GPU_COLORS.length],
    }))
}

function buildPowerSeries(history) {
  if (!history) return []
  return [
    {
      name: 'System total',
      color: '#facc15',
      points: history.map((r) => ({
        t: new Date(r.timestamp + 'Z').getTime(),
        v: r.total_watts == null ? null : Number(r.total_watts),
      })),
    },
  ]
}

function SystemPowerStats({ current, daySummary, weekSummary, psuWatts, psuPercent }) {
  const warn = psuWatts && psuPercent != null && psuPercent >= 80
  const crit = psuWatts && psuPercent != null && psuPercent >= 95
  const tone = crit ? 'critical' : warn ? 'warning' : 'default'
  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2">
      <StatTile
        label="Now Total"
        value={fmtNum(current?.total_watts, ' W')}
        sub={current?.source ? `via ${current.source}` : null}
        tone={tone}
      />
      <StatTile label="CPU" value={fmtNum(current?.cpu_watts, ' W', 1)} />
      <StatTile label="GPUs" value={fmtNum(current?.gpu_watts, ' W', 1)} />
      <StatTile label="Day High" value={fmtNum(daySummary?.total_max, ' W')} />
      <StatTile label="Day Idle" value={fmtNum(daySummary?.total_min, ' W')} />
      <StatTile
        label="Week High"
        value={fmtNum(weekSummary?.total_max, ' W')}
        sub={
          psuWatts
            ? `PSU ${psuWatts}W · ${fmtNum(psuPercent, '%')} now`
            : 'set thresholds.psu_watts'
        }
      />
    </div>
  )
}

const RANGES = [
  { label: '24h', hours: 24 },
  { label: '3d', hours: 72 },
  { label: '7d', hours: 168 },
]

function RangeSelector({ value, onChange }) {
  return (
    <div className="inline-flex bg-immich-bg border border-immich-border rounded-lg p-0.5">
      {RANGES.map((r) => (
        <button
          key={r.hours}
          type="button"
          onClick={() => onChange(r.hours)}
          className={`px-2.5 py-1 text-xs font-medium rounded-md transition-colors ${
            value === r.hours
              ? 'bg-immich-primary text-white'
              : 'text-immich-muted hover:text-immich-text'
          }`}
        >
          {r.label}
        </button>
      ))}
    </div>
  )
}

export default function GpuPanel() {
  const [hours, setHours] = useState(168)
  const { data: current, isLoading: loadingCurrent } = useGpuCurrent()
  const { data: summary, isLoading: loadingSummary } = useGpuSummary()
  const { data: history, isLoading: loadingHistory } = useGpuHistory(hours)

  const tempSeries = useMemo(
    () => buildSeriesByGpu(history?.gpu_metrics, 'temperature_c'),
    [history],
  )
  const utilSeries = useMemo(
    () => buildSeriesByGpu(history?.gpu_metrics, 'util_percent'),
    [history],
  )
  const powerSeriesGpu = useMemo(
    () => buildSeriesByGpu(history?.gpu_metrics, 'power_draw_w'),
    [history],
  )
  const powerSeriesSystem = useMemo(
    () => buildPowerSeries(history?.system_power),
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
  const psuPercent = current?.psu_percent ?? null

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
            server-manager service's PATH. System-wall power continues to be sampled when available.
          </div>
        </div>
        <div className="mt-4">
          <SystemPowerStats
            current={current?.system_power}
            daySummary={summary?.day?.system_power}
            weekSummary={summary?.week?.system_power}
            psuWatts={psuWatts}
            psuPercent={psuPercent}
          />
        </div>
      </Section>
    )
  }

  const psuLine = psuWatts > 0 ? psuWatts * 0.95 : null

  return (
    <>
      <Section
        title="GPUs"
        icon={CpuChipIcon}
        action={<RangeSelector value={hours} onChange={setHours} />}
      >
        {gpus.length === 0 ? (
          <p className="text-sm text-immich-muted">Waiting for first sample…</p>
        ) : (
          <div className="space-y-5">
            {gpus.map((gpu) => (
              <div key={gpu.uuid ?? gpu.index} className="border border-immich-border rounded-xl p-4">
                <div className="flex items-center justify-between mb-3">
                  <div>
                    <div className="text-xs text-immich-muted uppercase tracking-wider">
                      GPU {gpu.index} · {gpu.vendor}
                    </div>
                    <div className="text-sm font-semibold text-immich-text">{gpu.name}</div>
                  </div>
                  {gpu.mem_total_mb && (
                    <div className="text-xs font-mono text-immich-muted">
                      VRAM {fmtNum(gpu.mem_used_mb, '', 0)} / {fmtNum(gpu.mem_total_mb, ' MB', 0)}
                    </div>
                  )}
                </div>
                <GpuStatGrid
                  gpu={gpu}
                  daySummary={daySummary.get(gpu.index)}
                  weekSummary={weekSummary.get(gpu.index)}
                />
              </div>
            ))}
          </div>
        )}

        <div className="grid grid-cols-1 xl:grid-cols-3 gap-5 mt-6">
          <div>
            <div className="flex items-center gap-1.5 text-xs text-immich-muted uppercase tracking-wider mb-2">
              <FireIcon className="w-3.5 h-3.5" />
              Temperature
            </div>
            <LineChart
              series={tempSeries}
              unit="°C"
              spanHours={hours}
              ariaLabel="GPU temperature over time"
              threshold={80}
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
              ariaLabel="GPU power draw over time"
            />
          </div>
        </div>

        {gpus.length > 0 && (
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-4 text-xs text-immich-muted">
            {gpus.map((gpu, i) => (
              <span key={gpu.uuid ?? gpu.index} className="inline-flex items-center gap-1.5">
                <span
                  className="inline-block w-3 h-0.5"
                  style={{ background: GPU_COLORS[i % GPU_COLORS.length] }}
                />
                GPU {gpu.index} {gpu.name}
              </span>
            ))}
          </div>
        )}
      </Section>

      <Section title="System Power" icon={BoltIcon}>
        <SystemPowerStats
          current={current?.system_power}
          daySummary={summary?.day?.system_power}
          weekSummary={summary?.week?.system_power}
          psuWatts={psuWatts}
          psuPercent={psuPercent}
        />
        <div className="mt-5">
          <LineChart
            series={powerSeriesSystem}
            unit=" W"
            spanHours={hours}
            ariaLabel="Total system power draw over time"
            threshold={psuLine}
          />
          {psuLine && (
            <p className="text-[11px] text-immich-muted mt-2">
              Yellow dashed line marks 95% of your {psuWatts}W PSU rail.
            </p>
          )}
          {!psuLine && (
            <p className="text-[11px] text-immich-muted mt-2">
              Set <code className="font-mono">thresholds.psu_watts</code> in config to overlay your PSU rail
              and enable headroom alerts.
            </p>
          )}
          {current?.system_power?.source === 'estimated' && (
            <p className="text-[11px] text-immich-muted mt-1">
              Estimate = CPU package (RAPL) + GPUs + {fmtNum(current?.system_power?.baseline_watts, ' W')} baseline.
              Install <code className="font-mono">ipmitool</code> for exact wall-power readings if your BMC supports DCMI.
            </p>
          )}
        </div>
      </Section>
    </>
  )
}
