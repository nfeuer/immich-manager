import { useState, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '../utils/api'
import { TrashIcon, XMarkIcon } from '@heroicons/react/24/outline'

// ─── Utilities ────────────────────────────────────────────────────────────────

function formatBytes(bytes) {
  if (!bytes) return '0 B'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`
}

function formatSeconds(s) {
  if (s < 60) return `~${s}s`
  return `~${Math.round(s / 60)} min`
}

// ─── Scan Panel ───────────────────────────────────────────────────────────────

function ScanPanel({ scanStatus, onScanStarted }) {
  const [activeTab, setActiveTab] = useState('quick')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [estimate, setEstimate] = useState(null)
  const [estimating, setEstimating] = useState(false)

  const isRunning = scanStatus?.status === 'running'

  const quickMutation = useMutation({
    mutationFn: () => apiFetch('/api/dedup/scan/quick', { method: 'POST' }),
    onSuccess: onScanStarted,
  })

  const deepMutation = useMutation({
    mutationFn: () =>
      apiFetch('/api/dedup/scan/deep', {
        method: 'POST',
        body: JSON.stringify({ date_from: dateFrom, date_to: dateTo }),
      }),
    onSuccess: onScanStarted,
  })

  const cancelMutation = useMutation({
    mutationFn: () => apiFetch('/api/dedup/scan', { method: 'DELETE' }),
    onSuccess: onScanStarted,
  })

  const handleEstimate = async () => {
    setEstimating(true)
    setEstimate(null)
    try {
      const result = await apiFetch('/api/dedup/scan/estimate', {
        method: 'POST',
        body: JSON.stringify({ date_from: dateFrom, date_to: dateTo }),
      })
      setEstimate(result)
    } finally {
      setEstimating(false)
    }
  }

  if (isRunning) {
    const { phase, hashed, total_assets, mode } = scanStatus
    const pct = total_assets > 0 ? Math.round((hashed / total_assets) * 100) : 0
    const label =
      phase === 'hashing'
        ? `Collecting hashes… ${hashed} / ${total_assets}`
        : 'Comparing hashes…'
    return (
      <div className="bg-immich-surface border border-immich-border rounded-xl p-5">
        <div className="flex items-center justify-between mb-3">
          <p className="text-immich-text text-sm font-medium">
            {mode === 'quick' ? 'Quick Scan' : 'Deep Scan'} running
          </p>
          <button
            data-testid="btn-cancel-scan"
            onClick={() => cancelMutation.mutate()}
            className="text-xs text-red-400 hover:text-red-300"
          >
            Cancel
          </button>
        </div>
        <div data-testid="scan-progress" className="w-full">
          <div className="w-full bg-immich-border rounded-full h-2 mb-1">
            <div
              className="bg-immich-primary h-2 rounded-full transition-all"
              style={{ width: `${pct}%` }}
            />
          </div>
          <p className="text-immich-muted text-xs">{label}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="bg-immich-surface border border-immich-border rounded-xl p-5">
      <div className="flex gap-2 mb-4">
        {['quick', 'deep'].map((tab) => (
          <button
            key={tab}
            data-testid={`tab-${tab}`}
            aria-selected={activeTab === tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
              activeTab === tab
                ? 'bg-immich-primary text-white'
                : 'text-immich-muted hover:text-immich-text'
            }`}
          >
            {tab === 'quick' ? 'Quick Scan' : 'Deep Scan'}
          </button>
        ))}
      </div>

      {activeTab === 'quick' ? (
        <div>
          <p className="text-immich-muted text-xs mb-3">
            Uses Immich's built-in detection. Scans your entire library instantly.
          </p>
          {quickMutation.error?.message?.includes('immich_unavailable') && (
            <p className="text-yellow-400 text-xs mb-3">
              Immich duplicate detection unavailable — try a Deep Scan instead.
            </p>
          )}
          <button
            onClick={() => quickMutation.mutate()}
            disabled={quickMutation.isPending}
            className="px-4 py-2 bg-immich-primary text-white text-sm font-medium rounded-lg hover:opacity-90 disabled:opacity-50"
          >
            {quickMutation.isPending ? 'Scanning…' : 'Run Quick Scan'}
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          <div className="flex gap-3">
            <div className="flex-1">
              <label className="text-immich-muted text-xs block mb-1">From</label>
              <input
                data-testid="input-date-from"
                type="date"
                value={dateFrom}
                onChange={(e) => { setDateFrom(e.target.value); setEstimate(null) }}
                className="w-full bg-immich-bg border border-immich-border rounded-lg px-3 py-1.5 text-immich-text text-sm"
              />
            </div>
            <div className="flex-1">
              <label className="text-immich-muted text-xs block mb-1">To</label>
              <input
                data-testid="input-date-to"
                type="date"
                value={dateTo}
                onChange={(e) => { setDateTo(e.target.value); setEstimate(null) }}
                className="w-full bg-immich-bg border border-immich-border rounded-lg px-3 py-1.5 text-immich-text text-sm"
              />
            </div>
          </div>

          {dateFrom && dateTo && (
            <button
              data-testid="btn-estimate"
              onClick={handleEstimate}
              disabled={estimating}
              className="text-immich-muted text-xs underline hover:text-immich-text"
            >
              {estimating ? 'Estimating…' : 'Estimate scan time'}
            </button>
          )}

          {estimate && (
            <div data-testid="estimate-result" className="text-immich-muted text-xs">
              ~{estimate.total_assets.toLocaleString()} photos · ~{estimate.needs_hashing.toLocaleString()} need hashing · {formatSeconds(estimate.estimated_seconds)}
            </div>
          )}

          {estimate?.warning && (
            <div
              data-testid="estimate-warning"
              className="bg-yellow-900/30 border border-yellow-700 rounded-lg px-3 py-2 text-yellow-300 text-xs"
            >
              This scan will download ~{estimate.needs_hashing.toLocaleString()} thumbnails and may take {formatSeconds(estimate.estimated_seconds)}. It will run in the background.
            </div>
          )}

          <button
            data-testid="btn-start-deep"
            onClick={() => deepMutation.mutate()}
            disabled={!dateFrom || !dateTo || deepMutation.isPending}
            className="px-4 py-2 bg-immich-primary text-white text-sm font-medium rounded-lg hover:opacity-90 disabled:opacity-50"
          >
            {deepMutation.isPending ? 'Starting…' : 'Start Deep Scan'}
          </button>
        </div>
      )}
    </div>
  )
}

// ─── Group Card (overview) ─────────────────────────────────────────────────────

function GroupCard({ group, onClick }) {
  const assets = group.assets || []
  const preview = assets.slice(0, 4)

  const recommended = assets.find((a) => a.asset_id === group.recommended_keep_id)
  const others = assets.filter((a) => a.asset_id !== group.recommended_keep_id)
  const keepMp = recommended?.megapixels
  const otherMp = others[0]?.megapixels
  const keepSize = recommended?.file_size_bytes
  const otherSize = others[0]?.file_size_bytes

  const metaDiff = keepMp && otherMp
    ? `${keepMp}MP vs ${otherMp}MP · ${formatBytes(keepSize)} vs ${formatBytes(otherSize)}`
    : null

  return (
    <button
      data-testid={`group-card-${group.id}`}
      onClick={onClick}
      className="bg-immich-surface border border-immich-border rounded-xl p-4 text-left hover:border-immich-primary transition-colors w-full"
    >
      <div className="flex gap-2 mb-3">
        {preview.map((asset) => (
          <div key={asset.asset_id} className="relative flex-1">
            <img
              src={asset.thumbnail_url}
              alt=""
              className="w-full aspect-square object-cover rounded-lg"
            />
            {asset.asset_id === group.recommended_keep_id && (
              <span
                data-testid="recommended-badge"
                className="absolute top-1 left-1 bg-immich-primary text-white text-[10px] px-1.5 py-0.5 rounded font-medium"
              >
                Keep
              </span>
            )}
          </div>
        ))}
      </div>
      <p className="text-immich-muted text-xs">
        {assets.length} duplicates{metaDiff ? ` · ${metaDiff}` : ''}
      </p>
    </button>
  )
}

// ─── Detail Panel ─────────────────────────────────────────────────────────────

function DetailPanel({ group, onClose }) {
  const [keepId, setKeepId] = useState(group.recommended_keep_id)
  const queryClient = useQueryClient()

  const resolveMutation = useMutation({
    mutationFn: () =>
      apiFetch(`/api/dedup/groups/${group.id}/resolve`, {
        method: 'POST',
        body: JSON.stringify({ keep_asset_id: keepId }),
      }),
    onSuccess: (data) => {
      if (data.resolved) {
        queryClient.invalidateQueries({ queryKey: ['dedup-groups'] })
        onClose()
      }
    },
  })

  const dismissMutation = useMutation({
    mutationFn: () =>
      apiFetch(`/api/dedup/groups/${group.id}`, { method: 'DELETE' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dedup-groups'] })
      onClose()
    },
  })

  const assets = group.assets || []

  return (
    <div
      data-testid="detail-panel"
      className="fixed inset-y-0 right-0 w-full max-w-2xl bg-immich-surface border-l border-immich-border shadow-xl z-50 overflow-y-auto"
    >
      <div className="flex items-center justify-between p-4 border-b border-immich-border">
        <h2 className="text-immich-text font-semibold">{assets.length} Similar Photos</h2>
        <button onClick={onClose} className="text-immich-muted hover:text-immich-text">
          <XMarkIcon className="w-5 h-5" />
        </button>
      </div>

      <div className="p-4 space-y-6">
        {/* Thumbnails */}
        <div className="flex gap-3">
          {assets.map((asset) => (
            <div key={asset.asset_id} className="flex-1">
              <button
                onClick={() => setKeepId(asset.asset_id)}
                className={`w-full rounded-xl overflow-hidden ring-2 transition-all ${
                  keepId === asset.asset_id
                    ? 'ring-immich-primary'
                    : 'ring-transparent opacity-60 hover:opacity-90'
                }`}
              >
                <img
                  src={asset.thumbnail_url}
                  alt=""
                  className="w-full aspect-square object-cover"
                />
              </button>
              {keepId === asset.asset_id && (
                <p className="text-center text-immich-primary text-xs mt-1 font-medium">
                  {asset.asset_id === group.recommended_keep_id ? '★ Recommended keep' : 'Selected keep'}
                </p>
              )}
            </div>
          ))}
        </div>

        {/* Metadata table */}
        <table className="w-full text-xs text-immich-muted">
          <thead>
            <tr className="border-b border-immich-border">
              <th className="text-left py-1 font-medium">Field</th>
              {assets.map((a) => (
                <th key={a.asset_id} className="text-left py-1 font-medium">
                  {a.filename || a.asset_id.slice(0, 8)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {[
              ['Resolution', (a) => a.megapixels ? `${a.megapixels}MP (${a.width}×${a.height})` : '—'],
              ['File size', (a) => formatBytes(a.file_size_bytes)],
              ['Date taken', (a) => a.date_taken ? new Date(a.date_taken).toLocaleDateString() : '—'],
              ['Camera', (a) => a.camera_model || '—'],
            ].map(([label, fmt]) => (
              <tr key={label} className="border-b border-immich-border/50">
                <td className="py-1.5">{label}</td>
                {assets.map((a) => (
                  <td key={a.asset_id} className="py-1.5">{fmt(a)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>

        {/* Actions */}
        {resolveMutation.data && !resolveMutation.data.resolved && (
          <p className="text-red-400 text-xs">
            Delete failed: {resolveMutation.data.detail}
          </p>
        )}

        <div className="flex items-center gap-3">
          <button
            data-testid="btn-delete-others"
            onClick={() => resolveMutation.mutate()}
            disabled={resolveMutation.isPending}
            className="flex items-center gap-1.5 px-4 py-2 bg-red-700 text-white text-sm font-medium rounded-lg hover:bg-red-600 disabled:opacity-50"
          >
            <TrashIcon className="w-4 h-4" />
            {resolveMutation.isPending ? 'Deleting…' : 'Delete others & close'}
          </button>
          <button
            onClick={() => dismissMutation.mutate()}
            disabled={dismissMutation.isPending}
            className="text-immich-muted text-sm hover:text-immich-text"
          >
            Skip (keep all)
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── Results Panel ─────────────────────────────────────────────────────────────

function ResultsPanel({ groupsData, isLoading }) {
  const [selectedGroup, setSelectedGroup] = useState(null)
  const [showResolved, setShowResolved] = useState(false)
  const queryClient = useQueryClient()

  const handleIncludeResolvedToggle = () => {
    setShowResolved((v) => !v)
    queryClient.invalidateQueries({ queryKey: ['dedup-groups'] })
  }

  const groups = groupsData?.groups ?? []
  const totalGroups = groupsData?.total_groups ?? 0
  const removable = groupsData?.total_removable_photos ?? 0
  const savings = groupsData?.total_savings_bytes ?? 0

  if (isLoading) return <p className="text-immich-muted text-sm">Loading…</p>

  return (
    <div>
      {totalGroups > 0 && (
        <div className="flex items-center justify-between mb-4">
          <p className="text-immich-muted text-sm">
            {totalGroups} duplicate groups · {removable} photos removable · {formatBytes(savings)} savings
          </p>
          <button
            onClick={handleIncludeResolvedToggle}
            className="text-immich-muted text-xs underline hover:text-immich-text"
          >
            {showResolved ? 'Hide resolved' : 'Show resolved'}
          </button>
        </div>
      )}

      {groups.length === 0 ? (
        <div data-testid="no-groups-message" className="text-center py-16 text-immich-muted">
          No duplicates found. Run a scan to check your library.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {groups.map((group) => (
            <div key={group.id} className={group.resolved ? 'opacity-40' : ''}>
              <GroupCard
                group={group}
                onClick={() => !group.resolved && setSelectedGroup(group)}
              />
            </div>
          ))}
        </div>
      )}

      {selectedGroup && (
        <DetailPanel
          group={selectedGroup}
          onClose={() => setSelectedGroup(null)}
        />
      )}
    </div>
  )
}

// ─── Page ──────────────────────────────────────────────────────────────────────

export default function Duplicates() {
  const queryClient = useQueryClient()

  const { data: scanStatus } = useQuery({
    queryKey: ['dedup-scan-status'],
    queryFn: () => apiFetch('/api/dedup/scan/status'),
    refetchInterval: (query) =>
      query.state.data?.status === 'running' ? 2000 : false,
  })

  const { data: groupsData, isLoading: groupsLoading } = useQuery({
    queryKey: ['dedup-groups'],
    queryFn: () => apiFetch('/api/dedup/groups'),
  })

  const handleScanStarted = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['dedup-scan-status'] })
    queryClient.invalidateQueries({ queryKey: ['dedup-groups'] })
  }, [queryClient])

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-immich-text text-2xl font-semibold">Duplicates</h1>
      <ScanPanel scanStatus={scanStatus} onScanStarted={handleScanStarted} />
      <ResultsPanel groupsData={groupsData} isLoading={groupsLoading} />
    </div>
  )
}
