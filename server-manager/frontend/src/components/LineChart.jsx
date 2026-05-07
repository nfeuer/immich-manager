// Lightweight inline-SVG time-series chart with hover crosshair, gap
// breaking, and configurable y-axis behavior. No charting library.
//
// Each series is { name, color, points: [{t: epoch_ms, v: number|null}] }.

import { useMemo, useRef, useState } from 'react'

const DEFAULT_HEIGHT = 200
const PADDING = { top: 12, right: 12, bottom: 28, left: 48 }

function formatXTick(date, spanHours) {
  const d = new Date(date)
  if (spanHours <= 36) {
    return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
  }
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' })
}

function formatHover(date) {
  const d = new Date(date)
  return d.toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

function niceBounds(min, max, anchorZero) {
  if (!isFinite(min) || !isFinite(max)) return [0, 1]
  if (min === max) {
    if (anchorZero) return [0, max + 1]
    return [Math.max(0, min - 5), max + 5]
  }
  if (anchorZero) return [0, max * 1.08]
  // Pad below by 5% of range, above by 8% — gives breathing room without
  // the temperature line sliding off the bottom edge on cool data.
  const range = max - min
  const lo = Math.max(0, min - range * 0.08)
  const hi = max + range * 0.08
  return [lo, hi]
}

function pickXTicks(times, spanHours) {
  if (times.length === 0) return []
  const desired = 6
  const stride = Math.max(1, Math.floor(times.length / desired))
  const ticks = []
  for (let i = 0; i < times.length; i += stride) ticks.push(i)
  if (ticks[ticks.length - 1] !== times.length - 1) ticks.push(times.length - 1)
  return ticks.map((i) => ({ idx: i, label: formatXTick(times[i], spanHours) }))
}

// Build an SVG path string while breaking the line whenever consecutive
// timestamps are further apart than `gapMs` — keeps service-downtime gaps
// from being silently bridged.
function buildPath(points, xScale, yScale, gapMs) {
  if (points.length === 0) return ''
  let path = ''
  let pen = 'M'
  let prevT = null
  for (const p of points) {
    if (p.v == null || !isFinite(p.v)) {
      pen = 'M'
      prevT = null
      continue
    }
    if (prevT != null && p.t - prevT > gapMs) pen = 'M'
    path += `${pen}${xScale(p.t).toFixed(2)},${yScale(p.v).toFixed(2)} `
    pen = 'L'
    prevT = p.t
  }
  return path.trim()
}

export default function LineChart({
  series,
  width = 720,
  height = DEFAULT_HEIGHT,
  unit = '',
  fmt,
  yMax,
  yMin,                 // 'auto' | number — controls lower bound
  spanHours = 168,
  threshold,
  thresholdLabel,
  ariaLabel,
  gapMinutes = 10,      // break the line if consecutive samples are further apart
  stacked = false,      // stacked-area chart for additive series
}) {
  const svgRef = useRef(null)
  const [hover, setHover] = useState(null)

  const computed = useMemo(() => {
    const allPoints = series.flatMap((s) => s.points)
    if (allPoints.length === 0) return null

    const tMin = Math.min(...allPoints.map((p) => p.t))
    const tMax = Math.max(...allPoints.map((p) => p.t))

    const innerW = width - PADDING.left - PADDING.right
    const innerH = height - PADDING.top - PADDING.bottom

    const xScale = (t) =>
      PADDING.left + ((t - tMin) / Math.max(1, tMax - tMin)) * innerW

    let yLo, yHi
    if (stacked) {
      // Build per-timestamp totals for stack height (assumes aligned timestamps).
      const totals = {}
      for (const s of series) {
        for (const p of s.points) {
          if (p.v == null || !isFinite(p.v)) continue
          totals[p.t] = (totals[p.t] || 0) + p.v
        }
      }
      const totalValues = Object.values(totals)
      ;[yLo, yHi] = niceBounds(0, Math.max(...totalValues, 1), true)
    } else {
      const values = allPoints.map((p) => p.v).filter((v) => v != null && isFinite(v))
      const anchorZero = yMin == null
      ;[yLo, yHi] = niceBounds(Math.min(...values), Math.max(...values), anchorZero)
      if (yMin === 'auto') {
        // Already computed with anchorZero false above? No — pass through.
        const values2 = allPoints.map((p) => p.v).filter((v) => v != null && isFinite(v))
        ;[yLo, yHi] = niceBounds(Math.min(...values2), Math.max(...values2), false)
      } else if (typeof yMin === 'number') {
        yLo = yMin
      }
    }
    if (yMax != null) yHi = Math.max(yHi, yMax)

    const yScale = (v) =>
      PADDING.top + (1 - (v - yLo) / Math.max(1e-9, yHi - yLo)) * innerH

    const gridLines = []
    for (let i = 0; i <= 4; i++) {
      const v = yLo + (yHi - yLo) * (i / 4)
      gridLines.push({ y: yScale(v), label: fmt ? fmt(v) : v.toFixed(yHi >= 100 ? 0 : 1) })
    }

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

    const gapMs = gapMinutes * 60_000

    let seriesPaths
    if (stacked) {
      // Build cumulative sums per timestamp so each layer sits atop the previous.
      const sortedPoints = series.map((s) =>
        s.points
          .filter((p) => p.v != null && isFinite(p.v))
          .sort((a, b) => a.t - b.t),
      )
      // Use the union of timestamps for area boundaries.
      const allTs = [
        ...new Set(sortedPoints.flat().map((p) => p.t)),
      ].sort((a, b) => a - b)
      const cum = new Map(allTs.map((t) => [t, 0]))
      seriesPaths = series.map((s, i) => {
        const map = new Map(sortedPoints[i].map((p) => [p.t, p.v]))
        let path = ''
        let upper = []
        for (const t of allTs) {
          const v = map.get(t)
          if (v == null) continue
          const baseline = cum.get(t)
          const top = baseline + v
          cum.set(t, top)
          upper.push({ t, baseline, top })
        }
        if (upper.length === 0) return { ...s, path: '' }
        // Top edge left→right
        path += `M${xScale(upper[0].t).toFixed(2)},${yScale(upper[0].top).toFixed(2)} `
        for (let k = 1; k < upper.length; k++) {
          path += `L${xScale(upper[k].t).toFixed(2)},${yScale(upper[k].top).toFixed(2)} `
        }
        // Bottom edge right→left
        for (let k = upper.length - 1; k >= 0; k--) {
          path += `L${xScale(upper[k].t).toFixed(2)},${yScale(upper[k].baseline).toFixed(2)} `
        }
        path += 'Z'
        return { ...s, path }
      })
    } else {
      seriesPaths = series.map((s) => ({
        ...s,
        path: buildPath(s.points, xScale, yScale, gapMs),
      }))
    }

    // Pre-sort points by time for hover lookup.
    const hoverSeries = series.map((s) => ({
      ...s,
      sorted: [...s.points]
        .filter((p) => p.v != null && isFinite(p.v))
        .sort((a, b) => a.t - b.t),
    }))

    return {
      gridLines,
      xTicks,
      seriesPaths,
      thresholdY: threshold != null ? yScale(threshold) : null,
      yLo,
      yHi,
      tMin,
      tMax,
      xScale,
      yScale,
      innerW,
      hoverSeries,
    }
  }, [series, width, height, yMax, yMin, threshold, spanHours, gapMinutes, stacked, fmt])

  if (!computed) {
    return (
      <div
        className="flex items-center justify-center text-xs text-immich-muted"
        style={{ height }}
      >
        No data yet — first sample arrives within a minute.
      </div>
    )
  }

  function onMouseMove(e) {
    const svg = svgRef.current
    if (!svg) return
    const rect = svg.getBoundingClientRect()
    // Map screen x → SVG viewBox x.
    const xRatio = (e.clientX - rect.left) / rect.width
    const svgX = xRatio * width
    if (svgX < PADDING.left || svgX > width - PADDING.right) {
      setHover(null)
      return
    }
    // Invert x scale to find approximate timestamp.
    const t =
      computed.tMin +
      ((svgX - PADDING.left) / computed.innerW) * (computed.tMax - computed.tMin)
    setHover({ t, svgX })
  }

  function onMouseLeave() {
    setHover(null)
  }

  // Find the nearest sample per series for the hover crosshair.
  const hoverValues = hover
    ? computed.hoverSeries.map((s) => {
        if (s.sorted.length === 0) return { ...s, point: null }
        let lo = 0
        let hi = s.sorted.length - 1
        while (lo < hi) {
          const mid = (lo + hi) >> 1
          if (s.sorted[mid].t < hover.t) lo = mid + 1
          else hi = mid
        }
        const candA = s.sorted[Math.max(0, lo - 1)]
        const candB = s.sorted[lo]
        const point =
          Math.abs(candA.t - hover.t) <= Math.abs(candB.t - hover.t) ? candA : candB
        return { ...s, point }
      })
    : []

  const hoverX = hoverValues.length > 0 && hoverValues[0].point
    ? computed.xScale(hoverValues[0].point.t)
    : null

  const formatValue = fmt
    ? (v) => fmt(v)
    : (v) => `${v.toFixed(computed.yHi >= 100 ? 0 : 1)}${unit}`

  return (
    <div className="relative">
      <svg
        ref={svgRef}
        width="100%"
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
        role="img"
        aria-label={ariaLabel}
        className="block"
        onMouseMove={onMouseMove}
        onMouseLeave={onMouseLeave}
      >
        {computed.gridLines.map((g, i) => (
          <g key={`g-${i}`}>
            <line
              x1={PADDING.left}
              x2={width - PADDING.right}
              y1={g.y}
              y2={g.y}
              stroke="#2a2a3d"
              strokeWidth="1"
              strokeDasharray="2 3"
            />
            <text
              x={PADDING.left - 6}
              y={g.y + 3}
              textAnchor="end"
              fontSize="10"
              fill="#7c7c9a"
              fontFamily="ui-monospace, SFMono-Regular, Menlo, monospace"
            >
              {g.label}
              {unit && !fmt ? unit : ''}
            </text>
          </g>
        ))}

        {computed.thresholdY != null && (
          <g>
            <line
              x1={PADDING.left}
              x2={width - PADDING.right}
              y1={computed.thresholdY}
              y2={computed.thresholdY}
              stroke="#facc15"
              strokeWidth="1"
              strokeDasharray="4 3"
            />
            {thresholdLabel && (
              <text
                x={width - PADDING.right - 4}
                y={computed.thresholdY - 4}
                textAnchor="end"
                fontSize="9"
                fill="#facc15"
              >
                {thresholdLabel}
              </text>
            )}
          </g>
        )}

        {computed.seriesPaths.map((s) =>
          stacked ? (
            <path
              key={s.name}
              d={s.path}
              fill={s.color}
              fillOpacity="0.7"
              stroke={s.color}
              strokeWidth="0.5"
            />
          ) : (
            <path
              key={s.name}
              d={s.path}
              fill="none"
              stroke={s.color}
              strokeWidth="1.75"
              strokeLinejoin="round"
              strokeLinecap="round"
            />
          ),
        )}

        {hoverX != null && (
          <line
            x1={hoverX}
            x2={hoverX}
            y1={PADDING.top}
            y2={height - PADDING.bottom}
            stroke="#7c7c9a"
            strokeWidth="0.75"
            strokeDasharray="2 2"
          />
        )}
        {hoverValues.map((s) =>
          s.point ? (
            <circle
              key={`dot-${s.name}`}
              cx={computed.xScale(s.point.t)}
              cy={computed.yScale(s.point.v)}
              r={3}
              fill={s.color}
              stroke="#0f0f11"
              strokeWidth="1.5"
            />
          ) : null,
        )}

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

      {hover && hoverValues.some((s) => s.point) && (
        <div
          className="absolute pointer-events-none bg-immich-bg border border-immich-border rounded-md text-[11px] px-2 py-1.5 shadow-lg z-10"
          style={{
            left: `min(calc(${(hoverX / width) * 100}% + 8px), calc(100% - 180px))`,
            top: 8,
            minWidth: 140,
          }}
        >
          <div className="text-immich-muted text-[10px] mb-1 font-mono">
            {formatHover(hoverValues.find((s) => s.point).point.t)}
          </div>
          {hoverValues.map((s) =>
            s.point ? (
              <div key={s.name} className="flex items-center justify-between gap-3">
                <span className="inline-flex items-center gap-1.5 text-immich-text">
                  <span
                    className="inline-block w-2 h-2 rounded-sm"
                    style={{ background: s.color }}
                  />
                  {s.name}
                </span>
                <span className="font-mono text-immich-text">{formatValue(s.point.v)}</span>
              </div>
            ) : null,
          )}
        </div>
      )}
    </div>
  )
}
