import { useState, useRef, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '../utils/api'

const SOURCES = [
  { id: 'google', label: 'Google Photos', desc: 'Import from a Google Takeout export' },
  { id: 'apple', label: 'Apple Photos', desc: 'Import from an Apple Photos export (File → Export Originals)' },
  { id: 'icloud', label: 'iCloud Photos', desc: 'Import from Apple data export (privacy.apple.com)' },
  { id: 'folder', label: 'Local / External Drive', desc: 'Import photos from any folder — no special export format needed' },
]

// Derived from SOURCES for O(1) lookup by id in step 1 and step 2
const SOURCE_LABELS = Object.fromEntries(SOURCES.map(s => [s.id, s.label]))

const TERMINAL = ['completed', 'failed', 'cancelled']

export default function Import() {
  const [step, setStep] = useState(0)
  const [source, setSource] = useState(null)
  const [files, setFiles] = useState(null)
  const [dragOver, setDragOver] = useState(false)
  const fileInputRef = useRef(null)

  const handleFileChange = (e) => {
    const f = e.target.files
    setFiles(f?.length > 0 ? f : null)
  }

  const handleDrop = (e) => {
    e.preventDefault()
    setDragOver(false)
    const f = e.dataTransfer.files
    setFiles(f?.length > 0 ? f : null)
  }

  const queryClient = useQueryClient()
  const [jobId, setJobId] = useState(null)

  // Poll job status every 2s; stop when terminal
  const jobQuery = useQuery({
    queryKey: ['importJob', jobId],
    queryFn: () => apiFetch(`/api/import/jobs/${jobId}`),
    enabled: !!jobId,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return TERMINAL.includes(status) ? false : 2000
    },
  })

  const historyQuery = useQuery({
    queryKey: ['importHistory'],
    queryFn: () => apiFetch('/api/import/jobs'),
  })

  // Invalidate history when job reaches terminal state (TanStack Query v5: no onSuccess on useQuery)
  useEffect(() => {
    const status = jobQuery.data?.status
    if (TERMINAL.includes(status)) {
      queryClient.invalidateQueries({ queryKey: ['importHistory'] })
    }
  }, [jobQuery.data?.status, queryClient])

  // Upload mutation — must use raw fetch (not apiFetch) because apiFetch forces Content-Type: application/json
  const uploadMutation = useMutation({
    mutationFn: async () => {
      const formData = new FormData()
      formData.append('source_type', source)
      for (const file of files) {
        formData.append('files', file, file.webkitRelativePath || file.name)
      }
      const res = await fetch('/api/import/upload', {
        method: 'POST',
        body: formData,
        credentials: 'include',
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || `Upload failed (${res.status})`)
      }
      return res.json()
    },
    onSuccess: (data) => {
      setJobId(data.job_id)
      setStep(2)
    },
  })

  const cancelJob = async () => {
    if (!jobId) return
    try {
      await fetch(`/api/import/jobs/${jobId}`, { method: 'DELETE', credentials: 'include' })
    } catch { /* best effort */ }
    // Refresh job status immediately after cancel attempt
    jobQuery.refetch()
  }

  const resetWizard = () => {
    setStep(0)
    setSource(null)
    setFiles(null)
    setJobId(null)
    uploadMutation.reset()
  }

  const job = jobQuery.data
  const isJobRunning = job && !TERMINAL.includes(job.status)

  return (
    <div className="p-6 max-w-2xl mx-auto">
      <h1 className="text-immich-text text-2xl font-semibold mb-6">Import Photos</h1>

      {step === 0 && (
        <div className="space-y-3">
          {SOURCES.map(s => (
            <button
              key={s.id}
              onClick={() => { setSource(s.id); setStep(1) }}
              className="w-full text-left p-4 rounded-xl border border-immich-border bg-immich-surface hover:border-immich-primary transition-colors"
            >
              <p className="text-immich-text font-medium">{s.label}</p>
              <p className="text-immich-muted text-sm mt-0.5">{s.desc}</p>
            </button>
          ))}
        </div>
      )}

      {step === 1 && (
        <div className="space-y-4">
          <div className="flex items-center gap-2 mb-2">
            <button
              onClick={() => setStep(0)}
              className="text-immich-primary text-sm hover:underline"
            >
              ← Back
            </button>
            <span data-testid="selected-source-label" className="text-immich-muted text-sm">
              {SOURCE_LABELS[source]}
            </span>
          </div>

          <div
            data-testid="file-drop-zone"
            onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors ${
              dragOver
                ? 'border-immich-primary bg-immich-primary/5'
                : 'border-immich-border hover:border-immich-primary'
            }`}
          >
            <p className="text-immich-muted mb-1">Click to select a folder, or drag and drop</p>
            <p className="text-immich-muted text-xs">Supports JPG, PNG, HEIC, MP4, MOV and more</p>
            <input
              ref={fileInputRef}
              data-testid="file-input"
              type="file"
              className="hidden"
              webkitdirectory=""
              multiple
              onChange={handleFileChange}
            />
          </div>

          {files !== null && files.length > 0 && (
            <p className="text-immich-text text-sm">{files.length} files ready to import</p>
          )}

          {uploadMutation.error && (
            <p className="text-red-400 text-sm">{uploadMutation.error.message}</p>
          )}

          <button
            data-testid="btn-start-import"
            disabled={!files || files.length === 0 || uploadMutation.isPending}
            onClick={() => uploadMutation.mutate()}
            className="px-4 py-2 bg-immich-primary text-white font-medium rounded-lg disabled:opacity-40"
          >
            Start Import
          </button>
        </div>
      )}

      {step === 2 && (
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <span className="text-immich-muted text-sm">{SOURCE_LABELS[source]}</span>
            {job?.status && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-immich-surface border border-immich-border text-immich-muted">
                {job.status}
              </span>
            )}
          </div>

          <div className="p-4 bg-immich-surface rounded-xl border border-immich-border space-y-4">
            {job && (
              <>
                {/* Progress bar */}
                <div>
                  <div className="flex justify-between text-sm mb-1">
                    <span className="text-immich-muted">Progress</span>
                    <span className="text-immich-text">
                      {(job.uploaded ?? 0) + (job.duplicates ?? 0) + (job.errors ?? 0)} / {job.total_files ?? 0}
                    </span>
                  </div>
                  <div className="w-full bg-immich-border rounded-full h-2">
                    <div
                      className="bg-immich-primary h-2 rounded-full transition-all"
                      style={{
                        width: job.total_files > 0
                          ? `${Math.round((((job.uploaded ?? 0) + (job.duplicates ?? 0) + (job.errors ?? 0)) / job.total_files) * 100)}%`
                          : '0%',
                      }}
                    />
                  </div>
                </div>

                {/* Stats grid */}
                <div className="grid grid-cols-4 gap-3 text-center">
                  <div>
                    <p data-testid="stat-uploaded" className="text-xl font-bold text-green-400">{job.uploaded ?? 0}</p>
                    <p className="text-xs text-immich-muted">Uploaded</p>
                  </div>
                  <div>
                    <p data-testid="stat-duplicates" className="text-xl font-bold text-yellow-400">{job.duplicates ?? 0}</p>
                    <p className="text-xs text-immich-muted">Duplicates</p>
                  </div>
                  <div>
                    <p data-testid="stat-errors" className="text-xl font-bold text-red-400">{job.errors ?? 0}</p>
                    <p className="text-xs text-immich-muted">Errors</p>
                  </div>
                  <div>
                    <p data-testid="stat-total" className="text-xl font-bold text-immich-text">{job.total_files ?? 0}</p>
                    <p className="text-xs text-immich-muted">Total</p>
                  </div>
                </div>
              </>
            )}

            {/* Error banner */}
            {job?.error_message && (
              <div data-testid="error-banner" className="p-3 bg-red-900/20 border border-red-700 rounded-lg text-red-400 text-sm">
                {job.error_message}
              </div>
            )}

            {/* Actions */}
            <div className="flex gap-2">
              {isJobRunning && (
                <button
                  data-testid="btn-cancel"
                  onClick={cancelJob}
                  className="px-3 py-1.5 bg-red-600 text-white text-sm rounded-lg hover:bg-red-700"
                >
                  Cancel
                </button>
              )}
              {TERMINAL.includes(job?.status) && (
                <button
                  data-testid="btn-new-import"
                  onClick={resetWizard}
                  className="px-3 py-1.5 bg-immich-surface text-immich-text text-sm rounded-lg border border-immich-border hover:bg-immich-border/40"
                >
                  New Import
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Import History */}
      <div className="mt-8">
        <h2 className="text-immich-text font-medium mb-3">Import History</h2>
        {historyQuery.isLoading && (
          <p className="text-immich-muted text-sm">Loading…</p>
        )}
        {historyQuery.isError && (
          <p className="text-red-400 text-sm">Failed to load import history.</p>
        )}
        {!historyQuery.isLoading && !historyQuery.isError && (
          <div data-testid="history-list" className="space-y-2">
            {historyQuery.data?.jobs?.length === 0 && (
              <p className="text-immich-muted text-sm">No import history yet.</p>
            )}
            {historyQuery.data?.jobs?.map(j => (
              <div
                key={j.id}
                data-testid={`history-item-${j.id}`}
                className="p-3 bg-immich-surface rounded-lg border border-immich-border flex items-center justify-between text-sm"
              >
                <div className="flex items-center gap-2">
                  <span className="text-immich-text font-medium">
                    {SOURCE_LABELS[j.source_type] ?? j.source_type}
                  </span>
                  <span className="text-immich-muted text-xs">
                    {new Date(j.created_at).toLocaleDateString()}
                  </span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-green-400">{j.uploaded ?? 0} uploaded</span>
                  <span className="text-yellow-400">{j.duplicates ?? 0} dupes</span>
                  <span className="text-red-400">{j.errors ?? 0} errors</span>
                  <span className="text-immich-muted">{j.status}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
