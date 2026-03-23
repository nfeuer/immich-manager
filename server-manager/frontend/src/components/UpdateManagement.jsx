import { useState, useEffect, useRef } from 'react'
import { ArrowPathIcon } from '@heroicons/react/24/outline'

export default function UpdateManagement() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [progressLines, setProgressLines] = useState([])
  const [updating, setUpdating] = useState(false)
  const progressRef = useRef(null)
  const esRef = useRef(null)

  async function load() {
    setLoading(true)
    try {
      const r = await fetch('/api/updates/status')
      if (!r.ok) throw new Error(r.status)
      setData(await r.json())
    } catch {
      setData(null)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  useEffect(() => {
    return () => {
      if (esRef.current) {
        esRef.current.close()
        esRef.current = null
      }
    }
  }, [])

  useEffect(() => {
    if (updating && progressRef.current) {
      progressRef.current.scrollTop = progressRef.current.scrollHeight
    }
  }, [progressLines, updating])

  async function applyUpdate() {
    if (!window.confirm('Apply the latest Immich update? A snapshot will be taken first and rollback is automatic on failure.')) return
    try {
      const r = await fetch('/api/updates/apply', { method: 'POST' })
      const d = await r.json()
      if (d.status === 'up_to_date') { window.alert('Already up to date.'); return }
      if (!r.ok) { window.alert(`Failed: ${d.detail ?? 'unknown error'}`); return }
      setUpdating(true)
      setProgressLines([])
      if (esRef.current) esRef.current.close()
      const es = new EventSource('/api/updates/apply/stream')
      esRef.current = es
      es.onmessage = (e) => {
        try {
          const obj = JSON.parse(e.data)
          setProgressLines((prev) => [...prev, { step: obj.step, message: `[${obj.step}] ${obj.message}` }])
          if (['done', 'rolled_back', 'error'].includes(obj.step)) {
            es.close()
            esRef.current = null
            setUpdating(false)
            load()
          }
        } catch {}
      }
      es.onerror = () => { es.close(); esRef.current = null }
    } catch (e) {
      window.alert(`Failed to start update: ${e.message}`)
    }
  }

  if (loading) {
    return (
      <div className="bg-immich-surface border border-immich-border rounded-2xl p-5 mb-6">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-immich-muted mb-4 flex items-center gap-1.5">
          <ArrowPathIcon className="w-3.5 h-3.5" /> Updates
        </h2>
        <p className="text-immich-muted text-sm">Loading version info…</p>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="bg-immich-surface border border-immich-border rounded-2xl p-5 mb-6">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-immich-muted mb-4">Updates</h2>
        <p className="text-red-400 text-sm">Failed to load update status.</p>
      </div>
    )
  }

  const upToDate = !data.update_available

  return (
    <div className="bg-immich-surface border border-immich-border rounded-2xl p-5 mb-6">
      <h2 className="text-xs font-semibold uppercase tracking-wider text-immich-muted mb-4 flex items-center gap-1.5">
        <ArrowPathIcon className="w-3.5 h-3.5" /> Updates
      </h2>

      <div className="flex flex-wrap items-center gap-4 mb-4">
        <span className="text-sm text-immich-muted">
          Current: <span className="font-mono font-semibold text-immich-text">v{data.current_version ?? '?'}</span>
        </span>
        <span className="text-sm text-immich-muted">
          Latest: <span className="font-mono font-semibold text-immich-text">v{data.latest_version ?? '?'}</span>
        </span>
        {data.changelog_url?.startsWith('https://github.com/') && (
          <a href={data.changelog_url} target="_blank" rel="noopener noreferrer"
            className="text-xs text-immich-primary hover:underline">
            View Changelog ↗
          </a>
        )}
        {!data.immich_reachable ? (
          <>
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-900/40 text-red-400 border border-red-800">
              Immich unreachable
            </span>
            <button
              onClick={() => { applyUpdate() }}
              disabled={updating}
              className="px-4 py-1.5 bg-amber-600 hover:bg-amber-500 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors duration-150"
            >
              Update anyway
            </button>
          </>
        ) : upToDate ? (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-900/40 text-green-400 border border-green-800">
            Up to date ✓
          </span>
        ) : (
          <>
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-900/40 text-blue-400 border border-blue-800">
              Update Available
            </span>
            <button
              onClick={() => { applyUpdate() }}
              disabled={updating}
              className="px-4 py-1.5 bg-immich-primary hover:bg-blue-600 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors duration-150"
            >
              Apply Update
            </button>
          </>
        )}
      </div>

      {updating && progressLines.length > 0 && (
        <pre
          ref={progressRef}
          className="bg-[#080810] text-gray-300 rounded-xl p-3 text-xs font-mono max-h-40 overflow-y-auto whitespace-pre-wrap mb-4"
        >
          {progressLines.map((l, i) => (
            <span key={i} className={
              l.step === 'done' ? 'text-green-400' :
              ['rolled_back', 'error'].includes(l.step) ? 'text-red-400' : ''
            }>
              {l.message}{'\n'}
            </span>
          ))}
        </pre>
      )}

      {(data.history ?? []).length > 0 && (
        <div className="border-t border-immich-border pt-4">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-immich-muted mb-3">History</h3>
          <table className="w-full text-sm">
            <tbody>
              {data.history.slice(0, 5).map((h, i) => (
                <tr key={i} className="border-b border-immich-border last:border-0">
                  <td className="py-1.5 pr-4 text-xs text-immich-muted">
                    {h.timestamp ? new Date(h.timestamp).toLocaleDateString() : '—'}
                  </td>
                  <td className="py-1.5 pr-4 font-mono text-xs text-immich-text">
                    v{h.from_version ?? '?'} → v{h.to_version ?? '?'}
                  </td>
                  <td className={`py-1.5 text-xs font-medium ${h.status === 'success' ? 'text-green-400' : 'text-red-400'}`}>
                    {h.status === 'success' ? '✓ success' : `✗ ${h.status}`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
