import { useState, useEffect } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { apiFetch } from '../utils/api'

export default function Preferences() {
  const { data } = useQuery({
    queryKey: ['preferences'],
    queryFn: () => apiFetch('/api/preferences'),
  })

  const [monthlyTarget, setMonthlyTarget] = useState(20)

  useEffect(() => {
    if (data?.monthly_target) setMonthlyTarget(data.monthly_target)
  }, [data])

  const saveMutation = useMutation({
    mutationFn: (prefs) =>
      apiFetch('/api/preferences', { method: 'POST', body: JSON.stringify(prefs) }),
  })

  return (
    <div className="p-6 max-w-lg">
      <h1 className="text-immich-text text-2xl font-semibold mb-6">Preferences</h1>

      {/* Album Settings */}
      <section className="bg-immich-surface border border-immich-border rounded-xl p-5 mb-4">
        <h2 className="text-immich-text font-medium mb-4">Album Settings</h2>
        <label className="block">
          <span className="text-immich-muted text-sm">Photos per album (default)</span>
          <input
            type="number"
            min={1}
            max={200}
            value={monthlyTarget}
            onChange={e => setMonthlyTarget(Number(e.target.value))}
            className="mt-1 w-full px-3 py-2 bg-immich-bg border border-immich-border rounded-lg text-immich-text text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-primary focus:border-immich-primary"
          />
        </label>
        <button
          onClick={() => saveMutation.mutate({ monthly_target: monthlyTarget })}
          disabled={saveMutation.isPending}
          className="mt-4 px-4 py-2 bg-immich-primary text-white font-medium rounded-lg disabled:opacity-50 text-sm focus-visible:ring-2 focus-visible:ring-immich-primary"
        >
          {saveMutation.isPending ? 'Saving…' : 'Save'}
        </button>
      </section>

      {/* AI Settings placeholder */}
      <section className="bg-immich-surface border border-immich-border rounded-xl p-5 mb-4">
        <h2 className="text-immich-text font-medium mb-2">AI Settings</h2>
        <p className="text-immich-muted text-sm">Advanced AI configuration coming soon.</p>
      </section>
    </div>
  )
}
