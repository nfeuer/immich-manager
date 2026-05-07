// Lightweight inline-SVG line chart. No chart library dependency.
//
// Single chart with one or more series, all sharing the same x-axis (timestamps).
// Designed for dashboard time-series — not interactive zoom or animation.

import { useMemo } from 'react'

const CHART_HEIGHT = 180
const CHART_PADDING = { top: 12, right: 12, bottom: 28, left: 44 }

function formatTick(date, spanHours) {
  const d = new Date(date)
  if (spanHours <= 36) {
    return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
  }
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' })
}

function niceBounds(min, max) {
  if (!isFinite(min) || !isFinite(max)) return [0, 1]
  if (min === max) return [Math.max(0, min - 1), max + 1]
  // Always anchor charts at zero — temp/util/power all start at 0.
  return [0, max * 1.08]
}

function pickXTicks(times, spanHours) {
  if (times.length === 0) return []
  const desired = 6
  const stride = Math.max(1, Math.floor(times.length / desired))
  const ticks = []
  for (let i = 0; i < times.length; i += stride) ticks.push(i)
  if (ticks[ticks.length - 1] !== times.length - 1) ticks.push(times.length - 1)
  return ticks.map((i) => ({ idx: i, label: formatTick(times[i], spanHours) }))
}

export default function LineChart({
  series,
  width = 720,
  height = CHART_HEIGHT,
  unit = '',
  yMax,
  spanHours = 168,
  threshold,
  ariaLabel,
}) {
  // Each `series` entry is { name, color, points: [{t: ms, v: number}, ...] }
  const computed = useMemo(() => {
    const allPoints = series.flatMap((s) => s.points)
    if (allPoints.length === 0) return null

    const xMin = Math.min(...allPoints.map((p) => p.t))
    const xMax = Math.max(...allPoints.map((p) => p.t))
    const yValues = allPoints.map((p) => p.v).filter((v) => v != null && isFinite(v))
    let [yLo, yHi] = niceBounds(Math.min(...yValues), Math.max(...yValues))
    if (yMax != null) yHi = Math.max(yHi, yMax)

    const innerW = width - CHART_PADDING.left - CHART_PADDING.right
    const innerH = height - CHART_PADDING.top - CHART_PADDING.bottom
    const xScale = (t) =>
      CHART_PADDING.left + ((t - xMin) / Math.max(1, xMax - xMin)) * innerW
    const yScale = (v) =>
      CHART_PADDING.top + (1 - (v - yLo) / Math.max(1e-9, yHi - yLo)) * innerH

    // Horizontal grid (5 lines)
    const gridLines = []
    for (let i = 0; i <= 4; i++) {
      const v = yLo + (yHi - yLo) * (i / 4)
      gridLines.push({ y: yScale(v), label: v.toFixed(yHi >= 100 ? 0 : 1) })
    }

    // X-axis tick samples drawn from the densest series
    const tickSeries = series.reduce(
      (best, s) => (s.points.length > best.points.length ? s : best),
      series[0],
    )
    const xTicks = pickXTicks(
      tickSeries.points.map((p) => p.t),
      spanHours,
    ).map(({ idx, label }) => ({
      x: xScale(tickSeries.points[idx].t),
      label,
    }))

    const seriesPaths = series.map((s) => {
      const pts = s.points.filter((p) => p.v != null && isFinite(p.v))
      if (pts.length === 0) return { ...s, path: '' }
      const path = pts
        .map((p, i) => `${i === 0 ? 'M' : 'L'}${xScale(p.t).toFixed(2)},${yScale(p.v).toFixed(2)}`)
        .join(' ')
      return { ...s, path }
    })

    return {
      gridLines,
      xTicks,
      seriesPaths,
      thresholdY: threshold != null ? yScale(threshold) : null,
      yLo,
      yHi,
    }
  }, [series, width, height, yMax, threshold, spanHours])

  if (!computed) {
    return (
      <div
        className="flex items-center justify-center text-xs text-immich-muted"
        style={{ height }}
      >
        No data yet — collection runs every minute.
      </div>
    )
  }

  return (
    <svg
      width="100%"
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      role="img"
      aria-label={ariaLabel}
      className="block"
    >
      {/* horizontal grid */}
      {computed.gridLines.map((g, i) => (
        <g key={`g-${i}`}>
          <line
            x1={CHART_PADDING.left}
            x2={width - CHART_PADDING.right}
            y1={g.y}
            y2={g.y}
            stroke="#2a2a3d"
            strokeWidth="1"
            strokeDasharray="2 3"
          />
          <text
            x={CHART_PADDING.left - 6}
            y={g.y + 3}
            textAnchor="end"
            fontSize="10"
            fill="#7c7c9a"
            fontFamily="ui-monospace, SFMono-Regular, Menlo, monospace"
          >
            {g.label}
            {unit}
          </text>
        </g>
      ))}

      {/* threshold line */}
      {computed.thresholdY != null && (
        <line
          x1={CHART_PADDING.left}
          x2={width - CHART_PADDING.right}
          y1={computed.thresholdY}
          y2={computed.thresholdY}
          stroke="#facc15"
          strokeWidth="1"
          strokeDasharray="4 3"
        />
      )}

      {/* series */}
      {computed.seriesPaths.map((s) => (
        <path
          key={s.name}
          d={s.path}
          fill="none"
          stroke={s.color}
          strokeWidth="1.75"
          strokeLinejoin="round"
          strokeLinecap="round"
        />
      ))}

      {/* x ticks */}
      {computed.xTicks.map((t, i) => (
        <text
          key={`x-${i}`}
          x={t.x}
          y={height - 8}
          textAnchor="middle"
          fontSize="10"
          fill="#7c7c9a"
        >
          {t.label}
        </text>
      ))}
    </svg>
  )
}
