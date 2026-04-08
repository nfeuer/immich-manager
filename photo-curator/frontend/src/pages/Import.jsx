import { useState, useRef, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '../utils/api'

const SOURCES = [
  { id: 'google', label: 'Google Photos', desc: 'Import from a Google Takeout export' },
  { id: 'apple', label: 'Apple Photos', desc: 'Import from an Apple Photos export (File → Export Originals)' },
  { id: 'icloud', label: 'iCloud Photos', desc: 'Import from Apple data export (privacy.apple.com)' },
  { id: 'folder', label: 'Local / External Drive', desc: 'Import photos from any folder — no special export format needed' },
  { id: 'server_path', label: 'Server Path (Large Import)', desc: 'Admin only — import directly from a directory already on the server. Best for 10k+ photos.', adminOnly: true },
]

// Derived from SOURCES for O(1) lookup by id in step 1 and step 2
const SOURCE_LABELS = Object.fromEntries(SOURCES.map(s => [s.id, s.label]))

const TERMINAL = ['completed', 'failed', 'cancelled']

export default function Import() {
  const authQuery = useQuery({
    queryKey: ['authCheck'],
    queryFn: () => apiFetch('/api/auth/check'),
    staleTime: 60_000,
  })
  const isAdmin = authQuery.data?.role === 'admin'

  const [step, setStep] = useState(0)
  const [source, setSource] = useState(null)
  const [files, setFiles] = useState(null)
  const [dragOver, setDragOver] = useState(false)
  const [serverPath, setServerPath] = useState('')
  const [serverPathSourceType, setServerPathSourceType] = useState('folder')
  const [createAlbums, setCreateAlbums] = useState(false)
  const [rootAlbum, setRootAlbum] = useState(false)
  const fileInputRef = useRef(null)

  const rootFolderName = source === 'server_path'
    ? serverPath.split('/').filter(Boolean).pop() ?? ''
    : (files?.[0]?.webkitRelativePath?.split('/')[0] ?? '')

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
      formData.append('create_albums', createAlbums)
      formData.append('root_album', rootAlbum)
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

  const serverPathMutation = useMutation({
    mutationFn: async () => {
      const res = await apiFetch('/api/import/start', {
        method: 'POST',
        body: JSON.stringify({
        source_type: serverPathSourceType,
        server_path: serverPath,
        create_albums: createAlbums,
        root_album: rootAlbum,
      }),
      })
      return res
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
    setServerPath('')
    setServerPathSourceType('folder')
    setCreateAlbums(false)
    setRootAlbum(false)
    uploadMutation.reset()
    serverPathMutation.reset()
  }

  const job = jobQuery.data
  const isJobRunning = job && !TERMINAL.includes(job.status)

  return (
    <div className="p-6 max-w-2xl mx-auto">
      <h1 className="text-immich-text text-2xl font-semibold mb-6">Import Photos</h1>

      {step === 0 && (
        <div className="space-y-3">
          {SOURCES.filter(s => !s.adminOnly || isAdmin).map(s => (
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

      {step === 1 && source !== 'server_path' && (
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

          {source === 'folder' && (
            <div className="space-y-2 pt-1">
              <label className="flex items-center gap-2 text-immich-text text-sm cursor-pointer">
                <input
                  type="checkbox"
                  checked={createAlbums}
                  onChange={e => { setCreateAlbums(e.target.checked); if (!e.target.checked) setRootAlbum(false) }}
                  className="rounded"
                />
                Create albums from subfolders
              </label>
              {createAlbums && (
                <label className="flex items-center gap-2 text-immich-text text-sm cursor-pointer ml-5">
                  <input
                    type="checkbox"
                    checked={rootAlbum}
                    onChange={e => setRootAlbum(e.target.checked)}
                    className="rounded"
                  />
                  Add loose photos to a &ldquo;{rootFolderName || 'root'}&rdquo; album
                </label>
              )}
            </div>
          )}

          {uploadMutation.error && (
            <p className="text-immich-error text-sm">{uploadMutation.error.message}</p>
          )}

          <button
            data-testid="btn-start-import"
            disabled={!files || files.length === 0 || uploadMutation.isPending}
            onClick={() => uploadMutation.mutate()}
            className="px-4 py-2 bg-immich-primary text-white font-medium rounded-lg disabled:opacity-40 focus-visible:ring-2 focus-visible:ring-immich-primary"
          >
            Start Import
          </button>
        </div>
      )}

      {step === 1 && source === 'server_path' && (
        <div className="space-y-4">
          <div className="flex items-center gap-2 mb-2">
            <button onClick={() => setStep(0)} className="text-immich-primary text-sm hover:underline">
              ← Back
            </button>
            <span className="text-immich-muted text-sm">Server Path Import</span>
          </div>

          <div className="p-4 bg-immich-surface rounded-xl border border-immich-border space-y-4">
            <div>
              <p className="text-immich-text text-sm font-medium mb-1">Server directory path</p>
              <p className="text-immich-muted text-xs mb-2">
                The photos must already be on the server (e.g. copied via rsync). The server will read
                directly from this path — nothing is re-uploaded through the browser.
              </p>
              <input
                data-testid="server-path-input"
                type="text"
                placeholder="/opt/photos-import"
                value={serverPath}
                onChange={(e) => setServerPath(e.target.value)}
                className="w-full px-3 py-2 bg-immich-bg border border-immich-border rounded-lg text-immich-text text-sm font-mono placeholder:text-immich-muted focus:outline-none focus:border-immich-primary"
              />
            </div>

            <div>
              <p className="text-immich-text text-sm font-medium mb-1">Photo source format</p>
              <select
                data-testid="server-path-source-type"
                value={serverPathSourceType}
                onChange={(e) => setServerPathSourceType(e.target.value)}
                className="w-full px-3 py-2 bg-immich-bg border border-immich-border rounded-lg text-immich-text text-sm focus:outline-none focus:border-immich-primary"
              >
                <option value="folder">Plain folder (any photos, no special format)</option>
                <option value="google">Google Takeout export</option>
                <option value="apple">Apple Photos export</option>
                <option value="icloud">iCloud data export</option>
              </select>
            </div>

            <div className="space-y-2">
              <label className="flex items-center gap-2 text-immich-text text-sm cursor-pointer">
                <input
                  type="checkbox"
                  checked={createAlbums}
                  onChange={e => { setCreateAlbums(e.target.checked); if (!e.target.checked) setRootAlbum(false) }}
                  className="rounded"
                />
                Create albums from subfolders
              </label>
              {createAlbums && (
                <label className="flex items-center gap-2 text-immich-text text-sm cursor-pointer ml-5">
                  <input
                    type="checkbox"
                    checked={rootAlbum}
                    onChange={e => setRootAlbum(e.target.checked)}
                    className="rounded"
                  />
                  Add loose photos to a &ldquo;{rootFolderName || 'root'}&rdquo; album
                </label>
              )}
            </div>
          </div>

          {serverPathMutation.error && (
            <p className="text-immich-error text-sm">{serverPathMutation.error.message}</p>
          )}

          <button
            data-testid="btn-start-import"
            disabled={!serverPath.trim() || serverPathMutation.isPending}
            onClick={() => serverPathMutation.mutate()}
            className="px-4 py-2 bg-immich-primary text-white font-medium rounded-lg disabled:opacity-40 focus-visible:ring-2 focus-visible:ring-immich-primary"
          >
            {serverPathMutation.isPending ? 'Starting…' : 'Start Import'}
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
                  <div className="flex items-center justify-between text-xs text-immich-muted mt-1">
                    <span>
                      {job.status === 'scanning' && 'Scanning\u2026'}
                      {job.status === 'running' && 'Uploading\u2026'}
                      {job.status === 'completed' && 'Done'}
                      {job.status === 'failed' && 'Failed'}
                      {job.status === 'cancelled' && 'Cancelled'}
                    </span>
                    {isJobRunning && job.current_file && (
                      <span className="font-mono truncate max-w-xs">{job.current_file}</span>
                    )}
                  </div>
                </div>

                {/* Stats grid */}
                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3 text-center">
                  <div>
                    <p data-testid="stat-uploaded" className="text-xl font-bold text-immich-success">{job.uploaded ?? 0}</p>
                    <p className="text-xs text-immich-muted">Uploaded</p>
                  </div>
                  <div>
                    <p data-testid="stat-albums" className="text-xl font-bold text-immich-info">{job.albums_created ?? 0}</p>
                    <p className="text-xs text-immich-muted">Albums</p>
                  </div>
                  <div>
                    <p data-testid="stat-duplicates" className="text-xl font-bold text-immich-warning">{job.duplicates ?? 0}</p>
                    <p className="text-xs text-immich-muted">Duplicates</p>
                  </div>
                  <div>
                    <p data-testid="stat-errors" className="text-xl font-bold text-immich-error">{job.errors ?? 0}</p>
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
              <div data-testid="error-banner" className="p-3 bg-immich-error-muted border border-immich-error-border rounded-lg text-immich-error text-sm">
                {job.error_message}
              </div>
            )}

            {/* Actions */}
            <div className="flex gap-2">
              {isJobRunning && (
                <button
                  data-testid="btn-cancel"
                  onClick={cancelJob}
                  className="px-3 py-1.5 bg-immich-error-border text-white text-sm rounded-lg hover:bg-immich-error focus-visible:ring-2 focus-visible:ring-immich-primary"
                >
                  Cancel
                </button>
              )}
              {TERMINAL.includes(job?.status) && (
                <button
                  data-testid="btn-new-import"
                  onClick={resetWizard}
                  className="px-3 py-1.5 bg-immich-surface text-immich-text text-sm rounded-lg border border-immich-border hover:bg-immich-border/40 focus-visible:ring-2 focus-visible:ring-immich-primary"
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
          <p className="text-immich-error text-sm">Failed to load import history.</p>
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
                  <span className="text-immich-success">{j.uploaded ?? 0} uploaded</span>
                  <span className="text-immich-warning">{j.duplicates ?? 0} dupes</span>
                  <span className="text-immich-error">{j.errors ?? 0} errors</span>
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
