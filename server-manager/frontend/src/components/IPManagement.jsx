import { useState } from 'react'
import { ShieldCheckIcon } from '@heroicons/react/24/outline'
import {
  useTrustedIPs, usePendingIPs, useRevokedIPs, useConnectionLog,
  useApproveIP, useRevokeIP, useUnblockIP, useDeleteIP, useUpdateIP,
} from '../hooks/useIPManagement.js'

const TABS = ['trusted', 'pending', 'blacklisted', 'connections']
const TAB_LABELS = { trusted: 'Trusted', pending: 'Pending', blacklisted: 'Blacklisted', connections: 'Connections' }
const DURATION_OPTIONS = ['24h', '7d', '30d', '90d', 'permanent']

function timeAgo(ts) {
  if (!ts) return '\u2014'
  const diff = Date.now() - new Date(ts).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  return `${days}d ago`
}

function TrustedTab() {
  const { data, isLoading } = useTrustedIPs()
  const revokeMut = useRevokeIP()
  const updateMut = useUpdateIP()
  const [editingIp, setEditingIp] = useState(null)
  const [editLabel, setEditLabel] = useState('')
  const [editDuration, setEditDuration] = useState('')
  const [revokeIp, setRevokeIp] = useState(null)
  const [revokeReason, setRevokeReason] = useState('')

  if (isLoading) return <p className="text-immich-muted text-sm">Loading...</p>
  const ips = data?.trusted || []

  return (
    <div>
      {/* Desktop table */}
      <div className="hidden md:block overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-immich-muted text-left border-b border-immich-border">
              <th scope="col" className="pb-2 pr-4">IP Address</th>
              <th scope="col" className="pb-2 pr-4">Label</th>
              <th scope="col" className="pb-2 pr-4">User</th>
              <th scope="col" className="pb-2 pr-4">Access</th>
              <th scope="col" className="pb-2 pr-4">Duration</th>
              <th scope="col" className="pb-2 pr-4">Expires</th>
              <th scope="col" className="pb-2 pr-4">Last Seen</th>
              <th scope="col" className="pb-2 pr-4">7d Conns</th>
              <th scope="col" className="pb-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {ips.map((ip) => (
              <tr key={ip.ip_address} className="border-b border-immich-border/50">
                <td className="py-2 pr-4 font-mono text-xs">{ip.ip_address}</td>
                <td className="py-2 pr-4">{ip.label || '\u2014'}</td>
                <td className="py-2 pr-4 text-xs">{ip.verified_by || '\u2014'}</td>
                <td className="py-2 pr-4">
                  <span className={`text-xs px-2 py-0.5 rounded ${ip.access_level === 'admin' ? 'bg-immich-error-muted text-immich-error' : 'bg-immich-info-muted text-immich-info'}`}>
                    {ip.access_level}
                  </span>
                </td>
                <td className="py-2 pr-4 text-xs">{ip.trust_duration}</td>
                <td className="py-2 pr-4 text-xs">{ip.expires_at ? new Date(ip.expires_at).toLocaleDateString() : 'Never'}</td>
                <td className="py-2 pr-4 text-xs">{timeAgo(ip.last_seen)}</td>
                <td className="py-2 pr-4 text-xs">{ip.connections_7d ?? 0}</td>
                <td className="py-2">
                  <div className="flex gap-1">
                    <button type="button" onClick={() => { setEditingIp(ip.ip_address); setEditLabel(ip.label || ''); setEditDuration(ip.trust_duration || '24h') }}
                      className="min-h-[44px] px-3 text-xs text-immich-info hover:bg-immich-info-muted rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-info">Edit</button>
                    <button type="button" onClick={() => setRevokeIp(ip.ip_address)}
                      className="min-h-[44px] px-3 text-xs text-immich-error hover:bg-immich-error-muted rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-error">Revoke</button>
                  </div>
                </td>
              </tr>
            ))}
            {ips.length === 0 && (
              <tr><td colSpan={9} className="py-4 text-center text-immich-muted">No trusted IPs</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Mobile cards */}
      <div className="md:hidden space-y-3">
        {ips.length === 0 ? (
          <p className="py-4 text-center text-immich-muted text-sm">No trusted IPs</p>
        ) : (
          ips.map((ip) => (
            <div key={ip.ip_address} className="bg-immich-bg border border-immich-border rounded-xl p-4">
              <div className="flex items-center justify-between mb-2 gap-2">
                <span className="font-mono text-sm break-all">{ip.ip_address}</span>
                <span className={`text-xs px-2 py-0.5 rounded flex-shrink-0 ${ip.access_level === 'admin' ? 'bg-immich-error-muted text-immich-error' : 'bg-immich-info-muted text-immich-info'}`}>
                  {ip.access_level}
                </span>
              </div>
              <dl className="space-y-1 text-xs mb-3">
                <div className="flex justify-between gap-2"><dt className="text-immich-muted">Label</dt><dd className="text-right">{ip.label || '—'}</dd></div>
                <div className="flex justify-between gap-2"><dt className="text-immich-muted">User</dt><dd className="text-right">{ip.verified_by || '—'}</dd></div>
                <div className="flex justify-between gap-2"><dt className="text-immich-muted">Duration</dt><dd className="text-right">{ip.trust_duration}</dd></div>
                <div className="flex justify-between gap-2"><dt className="text-immich-muted">Expires</dt><dd className="text-right">{ip.expires_at ? new Date(ip.expires_at).toLocaleDateString() : 'Never'}</dd></div>
                <div className="flex justify-between gap-2"><dt className="text-immich-muted">Last seen</dt><dd className="text-right">{timeAgo(ip.last_seen)}</dd></div>
                <div className="flex justify-between gap-2"><dt className="text-immich-muted">7d connections</dt><dd className="text-right">{ip.connections_7d ?? 0}</dd></div>
              </dl>
              <div className="flex gap-2">
                <button type="button" onClick={() => { setEditingIp(ip.ip_address); setEditLabel(ip.label || ''); setEditDuration(ip.trust_duration || '24h') }}
                  className="flex-1 min-h-[44px] text-sm text-immich-info border border-immich-info/40 hover:bg-immich-info-muted rounded-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-info">Edit</button>
                <button type="button" onClick={() => setRevokeIp(ip.ip_address)}
                  className="flex-1 min-h-[44px] text-sm text-immich-error border border-immich-error/40 hover:bg-immich-error-muted rounded-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-error">Revoke</button>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Edit panel */}
      {editingIp && (
        <div className="mt-4 p-4 bg-immich-bg border border-immich-border rounded-lg">
          <h4 className="text-sm font-medium mb-2">Edit {editingIp}</h4>
          <div className="flex gap-3 items-end flex-wrap">
            <div>
              <label htmlFor="edit-label" className="text-xs text-immich-muted block mb-1">Label</label>
              <input id="edit-label" value={editLabel} onChange={(e) => setEditLabel(e.target.value)}
                className="px-2 py-1 bg-immich-surface border border-immich-border rounded text-sm text-immich-text focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-primary" />
            </div>
            <div>
              <label htmlFor="edit-duration" className="text-xs text-immich-muted block mb-1">Duration</label>
              <select id="edit-duration" value={editDuration} onChange={(e) => setEditDuration(e.target.value)}
                className="px-2 py-1 bg-immich-surface border border-immich-border rounded text-sm text-immich-text focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-primary">
                {DURATION_OPTIONS.map((d) => <option key={d} value={d}>{d}</option>)}
              </select>
            </div>
            <button type="button" onClick={() => { updateMut.mutate({ ip: editingIp, label: editLabel, trust_duration: editDuration }); setEditingIp(null) }}
              className="px-3 py-2 bg-immich-primary hover:bg-immich-primary-hover text-white text-sm rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-primary min-h-[44px]">Save</button>
            <button type="button" onClick={() => setEditingIp(null)}
              className="px-3 py-2 text-immich-muted hover:text-immich-text text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-primary rounded min-h-[44px]">Cancel</button>
          </div>
        </div>
      )}

      {/* Revoke panel */}
      {revokeIp && (
        <div className="mt-4 p-4 bg-immich-bg border border-immich-error-border/50 rounded-lg">
          <h4 className="text-sm font-medium text-immich-error mb-2">Revoke {revokeIp}</h4>
          <label htmlFor="revoke-reason" className="sr-only">Reason for revoking</label>
          <input id="revoke-reason" value={revokeReason} onChange={(e) => setRevokeReason(e.target.value)}
            placeholder="Reason (optional)"
            className="w-full px-2 py-1 bg-immich-surface border border-immich-border rounded text-sm text-immich-text mb-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-error" />
          <div className="flex gap-2">
            <button type="button" onClick={() => { revokeMut.mutate({ ip_address: revokeIp, reason: revokeReason }); setRevokeIp(null); setRevokeReason('') }}
              className="px-3 py-2 bg-immich-error text-white text-sm rounded hover:bg-immich-error/90 focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-error min-h-[44px]">Confirm Revoke</button>
            <button type="button" onClick={() => { setRevokeIp(null); setRevokeReason('') }}
              className="px-3 py-2 text-immich-muted hover:text-immich-text text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-primary rounded min-h-[44px]">Cancel</button>
          </div>
        </div>
      )}
    </div>
  )
}

function PendingTab() {
  const { data, isLoading } = usePendingIPs()
  const approveMut = useApproveIP()
  const revokeMut = useRevokeIP()
  const [approveIp, setApproveIp] = useState(null)
  const [approveDuration, setApproveDuration] = useState('24h')
  const [approveLevel, setApproveLevel] = useState('user')

  if (isLoading) return <p className="text-immich-muted text-sm">Loading...</p>
  const ips = data?.pending || []

  return (
    <div>
      {/* Desktop table */}
      <div className="hidden md:block overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-immich-muted text-left border-b border-immich-border">
              <th scope="col" className="pb-2 pr-4">IP Address</th>
              <th scope="col" className="pb-2 pr-4">Source</th>
              <th scope="col" className="pb-2 pr-4">First Seen</th>
              <th scope="col" className="pb-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {ips.map((ip) => (
              <tr key={ip.ip_address} className="border-b border-immich-border/50">
                <td className="py-2 pr-4 font-mono text-xs">{ip.ip_address}</td>
                <td className="py-2 pr-4 text-xs">{ip.source}</td>
                <td className="py-2 pr-4 text-xs">{timeAgo(ip.created_at)}</td>
                <td className="py-2 flex gap-2">
                  <button type="button" onClick={() => setApproveIp(ip.ip_address)}
                    className="min-h-[44px] px-3 text-xs text-immich-success hover:text-immich-success/80 focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-success rounded">Approve</button>
                  <button type="button" onClick={() => revokeMut.mutate({ ip_address: ip.ip_address })}
                    className="min-h-[44px] px-3 text-xs text-immich-error hover:text-immich-error/80 focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-error rounded">Blacklist</button>
                </td>
              </tr>
            ))}
            {ips.length === 0 && (
              <tr><td colSpan={4} className="py-4 text-center text-immich-muted">No pending IPs</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Mobile cards */}
      <div className="md:hidden space-y-3">
        {ips.length === 0 ? (
          <p className="py-4 text-center text-immich-muted text-sm">No pending IPs</p>
        ) : (
          ips.map((ip) => (
            <div key={ip.ip_address} className="bg-immich-bg border border-immich-border rounded-xl p-4">
              <div className="mb-2">
                <span className="font-mono text-sm break-all">{ip.ip_address}</span>
              </div>
              <dl className="space-y-1 text-xs mb-3">
                <div className="flex justify-between gap-2"><dt className="text-immich-muted">Source</dt><dd className="text-right">{ip.source}</dd></div>
                <div className="flex justify-between gap-2"><dt className="text-immich-muted">First seen</dt><dd className="text-right">{timeAgo(ip.created_at)}</dd></div>
              </dl>
              <div className="flex gap-2">
                <button type="button" onClick={() => setApproveIp(ip.ip_address)}
                  className="flex-1 min-h-[44px] text-sm text-immich-success border border-immich-success/40 hover:bg-immich-success-muted rounded-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-success">Approve</button>
                <button type="button" onClick={() => revokeMut.mutate({ ip_address: ip.ip_address })}
                  className="flex-1 min-h-[44px] text-sm text-immich-error border border-immich-error/40 hover:bg-immich-error-muted rounded-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-error">Blacklist</button>
              </div>
            </div>
          ))
        )}
      </div>

      {approveIp && (
        <div className="mt-4 p-4 bg-immich-bg border border-immich-success-border/50 rounded-lg">
          <h4 className="text-sm font-medium text-immich-success mb-2">Approve {approveIp}</h4>
          <div className="flex gap-3 items-end">
            <div>
              <label htmlFor="approve-level" className="text-xs text-immich-muted block mb-1">Access Level</label>
              <select id="approve-level" value={approveLevel} onChange={(e) => setApproveLevel(e.target.value)}
                className="px-2 py-1 bg-immich-surface border border-immich-border rounded text-sm text-immich-text focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-success">
                <option value="user">User (Photo Curator only)</option>
                <option value="admin">Admin (All services)</option>
              </select>
            </div>
            <div>
              <label htmlFor="approve-duration" className="text-xs text-immich-muted block mb-1">Duration</label>
              <select id="approve-duration" value={approveDuration} onChange={(e) => setApproveDuration(e.target.value)}
                className="px-2 py-1 bg-immich-surface border border-immich-border rounded text-sm text-immich-text focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-success">
                {DURATION_OPTIONS.map((d) => <option key={d} value={d}>{d}</option>)}
              </select>
            </div>
            <button onClick={() => {
              approveMut.mutate({ ip_address: approveIp, access_level: approveLevel, trust_duration: approveDuration })
              setApproveIp(null)
            }} className="px-3 py-1 bg-immich-success text-white hover:bg-immich-success/90 text-sm rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-success">Confirm</button>
            <button type="button" onClick={() => setApproveIp(null)}
              className="px-3 py-1 text-immich-muted hover:text-immich-text text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-primary rounded">Cancel</button>
          </div>
        </div>
      )}
    </div>
  )
}

function BlacklistedTab() {
  const { data, isLoading } = useRevokedIPs()
  const unblockMut = useUnblockIP()
  const deleteMut = useDeleteIP()

  if (isLoading) return <p className="text-immich-muted text-sm">Loading...</p>
  const ips = data?.revoked || []

  return (
    <div>
      {/* Desktop table */}
      <div className="hidden md:block overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-immich-muted text-left border-b border-immich-border">
              <th scope="col" className="pb-2 pr-4">IP Address</th>
              <th scope="col" className="pb-2 pr-4">Original User</th>
              <th scope="col" className="pb-2 pr-4">Date Blacklisted</th>
              <th scope="col" className="pb-2 pr-4">Blacklisted By</th>
              <th scope="col" className="pb-2 pr-4">Reason</th>
              <th scope="col" className="pb-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {ips.map((ip) => (
              <tr key={ip.ip_address} className="border-b border-immich-border/50">
                <td className="py-2 pr-4 font-mono text-xs">{ip.ip_address}</td>
                <td className="py-2 pr-4 text-xs">{ip.verified_by || 'unknown'}</td>
                <td className="py-2 pr-4 text-xs">{ip.revoked_at ? new Date(ip.revoked_at).toLocaleDateString() : '\u2014'}</td>
                <td className="py-2 pr-4 text-xs">{ip.revoked_by || '\u2014'}</td>
                <td className="py-2 pr-4 text-xs">{ip.revoke_reason || '\u2014'}</td>
                <td className="py-2 flex gap-2">
                  <button type="button" onClick={() => unblockMut.mutate({ ip_address: ip.ip_address })}
                    className="min-h-[44px] px-3 text-xs text-immich-warning hover:text-immich-warning/80 focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-warning rounded">Unblock</button>
                  <button type="button" onClick={() => deleteMut.mutate(ip.ip_address)}
                    className="min-h-[44px] px-3 text-xs text-immich-error hover:text-immich-error/80 focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-error rounded">Delete</button>
                </td>
              </tr>
            ))}
            {ips.length === 0 && (
              <tr><td colSpan={6} className="py-4 text-center text-immich-muted">No blacklisted IPs</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Mobile cards */}
      <div className="md:hidden space-y-3">
        {ips.length === 0 ? (
          <p className="py-4 text-center text-immich-muted text-sm">No blacklisted IPs</p>
        ) : (
          ips.map((ip) => (
            <div key={ip.ip_address} className="bg-immich-bg border border-immich-border rounded-xl p-4">
              <div className="mb-2">
                <span className="font-mono text-sm break-all">{ip.ip_address}</span>
              </div>
              <dl className="space-y-1 text-xs mb-3">
                <div className="flex justify-between gap-2"><dt className="text-immich-muted">Original user</dt><dd className="text-right">{ip.verified_by || 'unknown'}</dd></div>
                <div className="flex justify-between gap-2"><dt className="text-immich-muted">Blacklisted</dt><dd className="text-right">{ip.revoked_at ? new Date(ip.revoked_at).toLocaleDateString() : '—'}</dd></div>
                <div className="flex justify-between gap-2"><dt className="text-immich-muted">By</dt><dd className="text-right">{ip.revoked_by || '—'}</dd></div>
                {ip.revoke_reason && <div className="flex justify-between gap-2"><dt className="text-immich-muted">Reason</dt><dd className="text-right">{ip.revoke_reason}</dd></div>}
              </dl>
              <div className="flex gap-2">
                <button type="button" onClick={() => unblockMut.mutate({ ip_address: ip.ip_address })}
                  className="flex-1 min-h-[44px] text-sm text-immich-warning border border-immich-warning/40 hover:bg-immich-warning-muted rounded-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-warning">Unblock</button>
                <button type="button" onClick={() => deleteMut.mutate(ip.ip_address)}
                  className="flex-1 min-h-[44px] text-sm text-immich-error border border-immich-error/40 hover:bg-immich-error-muted rounded-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-error">Delete</button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

function ConnectionsTab() {
  const [filters, setFilters] = useState({})
  const { data, isLoading } = useConnectionLog(filters)
  const connections = data?.connections || []

  return (
    <div>
      <div className="flex gap-3 mb-4">
        <label htmlFor="conn-filter-ip" className="sr-only">Filter by IP</label>
        <input id="conn-filter-ip" placeholder="Filter by IP" onChange={(e) => setFilters(f => ({ ...f, ip: e.target.value || undefined }))}
          className="px-2 py-1 bg-immich-bg border border-immich-border rounded text-sm text-immich-text w-40 focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-primary" />
        <label htmlFor="conn-filter-service" className="sr-only">Filter by service</label>
        <select id="conn-filter-service" onChange={(e) => setFilters(f => ({ ...f, service: e.target.value || undefined }))}
          className="px-2 py-1 bg-immich-bg border border-immich-border rounded text-sm text-immich-text focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-primary">
          <option value="">All services</option>
          <option value="server-manager">server-manager</option>
          <option value="photo-curator">photo-curator</option>
          <option value="ssh">ssh</option>
        </select>
        <label htmlFor="conn-filter-action" className="sr-only">Filter by action</label>
        <select id="conn-filter-action" onChange={(e) => setFilters(f => ({ ...f, action: e.target.value || undefined }))}
          className="px-2 py-1 bg-immich-bg border border-immich-border rounded text-sm text-immich-text focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-primary">
          <option value="">All actions</option>
          <option value="allowed">allowed</option>
          <option value="challenged">challenged</option>
          <option value="blocked">blocked</option>
          <option value="alert_sent">alert_sent</option>
        </select>
      </div>
      {isLoading ? (
        <p className="text-immich-muted text-sm">Loading...</p>
      ) : (
        <div className="overflow-x-auto max-h-64 sm:max-h-80 md:max-h-96 overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-immich-surface">
              <tr className="text-immich-muted text-left border-b border-immich-border">
                <th scope="col" className="pb-2 pr-4">Timestamp</th>
                <th scope="col" className="pb-2 pr-4">IP Address</th>
                <th scope="col" className="pb-2 pr-4">Service</th>
                <th scope="col" className="pb-2 pr-4">Action</th>
                <th scope="col" className="pb-2">User</th>
              </tr>
            </thead>
            <tbody>
              {connections.map((c, i) => (
                <tr key={i} className="border-b border-immich-border/50">
                  <td className="py-1.5 pr-4 text-xs">{timeAgo(c.timestamp)}</td>
                  <td className="py-1.5 pr-4 font-mono text-xs">{c.ip_address}</td>
                  <td className="py-1.5 pr-4 text-xs">{c.service}</td>
                  <td className="py-1.5 pr-4">
                    <span className={`text-xs ${
                      c.action === 'allowed' ? 'text-immich-success' :
                      c.action === 'blocked' ? 'text-immich-error' :
                      c.action === 'challenged' ? 'text-immich-warning' :
                      'text-immich-log-untagged'
                    }`}>{c.action}</span>
                  </td>
                  <td className="py-1.5 text-xs">{c.user_id || '\u2014'}</td>
                </tr>
              ))}
              {connections.length === 0 && (
                <tr><td colSpan={5} className="py-4 text-center text-immich-muted">No connections logged</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export default function IPManagement() {
  const [activeTab, setActiveTab] = useState('trusted')

  return (
    <div className="bg-immich-surface border border-immich-border rounded-2xl p-5 mb-6">
      <div className="flex items-center gap-2 mb-4">
        <ShieldCheckIcon className="w-5 h-5 text-immich-info" />
        <h2 className="text-lg font-semibold">IP Security</h2>
      </div>

      <div className="flex gap-1 mb-4 border-b border-immich-border">
        {TABS.map((tab) => (
          <button
            type="button"
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 text-sm transition-colors border-b-2 -mb-px focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-primary rounded-t ${
              activeTab === tab
                ? 'text-immich-info border-immich-info'
                : 'text-immich-muted border-transparent hover:text-immich-text'
            }`}
          >
            {TAB_LABELS[tab]}
          </button>
        ))}
      </div>

      {activeTab === 'trusted' && <TrustedTab />}
      {activeTab === 'pending' && <PendingTab />}
      {activeTab === 'blacklisted' && <BlacklistedTab />}
      {activeTab === 'connections' && <ConnectionsTab />}
    </div>
  )
}
