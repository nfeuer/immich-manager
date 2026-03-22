import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '../utils/api'

function StatCard({ label, value }) {
  return (
    <div className="bg-immich-surface border border-immich-border rounded-xl p-5">
      <p className="text-immich-muted text-sm">{label}</p>
      <p className="text-immich-text text-3xl font-semibold mt-1">{value ?? '—'}</p>
    </div>
  )
}

export default function Analytics({ onAuthError }) {
  const { data, isLoading } = useQuery({
    queryKey: ['analytics'],
    queryFn: () => apiFetch('/api/analytics'),
  })

  return (
    <div className="p-6">
      <h1 className="text-immich-text text-2xl font-semibold mb-6">Analytics</h1>
      {isLoading ? (
        <p className="text-immich-muted">Loading…</p>
      ) : (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
            <StatCard label="Total photos" value={data?.total_photos?.toLocaleString()} />
            <StatCard label="Months curated" value={data?.months_curated} />
            <StatCard label="Duplicates found" value={data?.duplicates_found} />
            <StatCard label="Faces identified" value={data?.faces_identified} />
          </div>
          <p className="text-immich-muted text-sm">Charts coming in a future release.</p>
        </>
      )}
    </div>
  )
}
