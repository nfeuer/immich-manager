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
  const ips = data?.ips || []

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-immich-muted text-left border-b border-immich-border">
            <th className="pb-2 pr-4">IP Address</th>
            <th className="pb-2 pr-4">Label</th>
            <th className="pb-2 pr-4">User</th>
            <th className="pb-2 pr-4">Access</th>
            <th className="pb-2 pr-4">Duration</th>
            <th className="pb-2 pr-4">Expires</th>
            <th className="pb-2 pr-4">Last Seen</th>
            <th className="pb-2 pr-4">7d Conns</th>
            <th className="pb-2">Actions</th>
          </tr>
        </thead>
        <tbody>
          {ips.map((ip) => (
            <tr key={ip.ip_address} className="border-b border-immich-border/50">
              <td className="py-2 pr-4 font-mono text-xs">{ip.ip_address}</td>
              <td className="py-2 pr-4">{ip.label || '\u2014'}</td>
              <td className="py-2 pr-4 text-xs">{ip.verified_by || '\u2014'}</td>
              <td className="py-2 pr-4">
                <span className={`text-xs px-2 py-0.5 rounded ${ip.access_level === 'admin' ? 'bg-red-500/20 text-red-300' : 'bg-blue-500/20 text-blue-300'}`}>
                  {ip.access_level}
                </span>
              </td>
              <td className="py-2 pr-4 text-xs">{ip.trust_duration}</td>
              <td className="py-2 pr-4 text-xs">{ip.expires_at ? new Date(ip.expires_at).toLocaleDateString() : 'Never'}</td>
              <td className="py-2 pr-4 text-xs">{timeAgo(ip.last_seen)}</td>
              <td className="py-2 pr-4 text-xs">{ip.connection_count_7d ?? 0}</td>
              <td className="py-2 flex gap-2">
                <button onClick={() => { setEditingIp(ip.ip_address); setEditLabel(ip.label || ''); setEditDuration(ip.trust_duration || '24h') }}
                  className="text-xs text-blue-400 hover:text-blue-300">Edit</button>
                <button onClick={() => setRevokeIp(ip.ip_address)}
                  className="text-xs text-red-400 hover:text-red-300">Revoke</button>
              </td>
            </tr>
          ))}
          {ips.length === 0 && (
            <tr><td colSpan={9} className="py-4 text-center text-immich-muted">No trusted IPs</td></tr>
          )}
        </tbody>
      </table>

      {editingIp && (
        <div className="mt-4 p-4 bg-immich-bg border border-immich-border rounded-lg">
          <h4 className="text-sm font-medium mb-2">Edit {editingIp}</h4>
          <div className="flex gap-3 items-end">
            <div>
              <label className="text-xs text-immich-muted block mb-1">Label</label>
              <input value={editLabel} onChange={(e) => setEditLabel(e.target.value)}
                className="px-2 py-1 bg-immich-surface border border-immich-border rounded text-sm text-immich-text" />
            </div>
            <div>
              <label className="text-xs text-immich-muted block mb-1">Duration</label>
              <select value={editDuration} onChange={(e) => setEditDuration(e.target.value)}
                className="px-2 py-1 bg-immich-surface border border-immich-border rounded text-sm text-immich-text">
                {DURATION_OPTIONS.map((d) => <option key={d} value={d}>{d}</option>)}
              </select>
            </div>
            <button onClick={() => { updateMut.mutate({ ip: editingIp, label: editLabel, trust_duration: editDuration }); setEditingIp(null) }}
              className="px-3 py-1 bg-blue-600 hover:bg-blue-700 text-white text-sm rounded">Save</button>
            <button onClick={() => setEditingIp(null)}
              className="px-3 py-1 text-immich-muted hover:text-immich-text text-sm">Cancel</button>
          </div>
        </div>
      )}

      {revokeIp && (
        <div className="mt-4 p-4 bg-immich-bg border border-red-800/50 rounded-lg">
          <h4 className="text-sm font-medium text-red-400 mb-2">Revoke {revokeIp}</h4>
          <input value={revokeReason} onChange={(e) => setRevokeReason(e.target.value)}
            placeholder="Reason (optional)"
            className="w-full px-2 py-1 bg-immich-surface border border-immich-border rounded text-sm text-immich-text mb-2" />
          <div className="flex gap-2">
            <button onClick={() => { revokeMut.mutate({ ip_address: revokeIp, reason: revokeReason }); setRevokeIp(null); setRevokeReason('') }}
              className="px-3 py-1 bg-red-600 hover:bg-red-700 text-white text-sm rounded">Confirm Revoke</button>
            <button onClick={() => { setRevokeIp(null); setRevokeReason('') }}
              className="px-3 py-1 text-immich-muted hover:text-immich-text text-sm">Cancel</button>
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
  const ips = data?.ips || []

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-immich-muted text-left border-b border-immich-border">
            <th className="pb-2 pr-4">IP Address</th>
            <th className="pb-2 pr-4">Source</th>
            <th className="pb-2 pr-4">First Seen</th>
            <th className="pb-2">Actions</th>
          </tr>
        </thead>
        <tbody>
          {ips.map((ip) => (
            <tr key={ip.ip_address} className="border-b border-immich-border/50">
              <td className="py-2 pr-4 font-mono text-xs">{ip.ip_address}</td>
              <td className="py-2 pr-4 text-xs">{ip.source}</td>
              <td className="py-2 pr-4 text-xs">{timeAgo(ip.created_at)}</td>
              <td className="py-2 flex gap-2">
                <button onClick={() => setApproveIp(ip.ip_address)}
                  className="text-xs text-green-400 hover:text-green-300">Approve</button>
                <button onClick={() => revokeMut.mutate({ ip_address: ip.ip_address })}
                  className="text-xs text-red-400 hover:text-red-300">Blacklist</button>
              </td>
            </tr>
          ))}
          {ips.length === 0 && (
            <tr><td colSpan={4} className="py-4 text-center text-immich-muted">No pending IPs</td></tr>
          )}
        </tbody>
      </table>

      {approveIp && (
        <div className="mt-4 p-4 bg-immich-bg border border-green-800/50 rounded-lg">
          <h4 className="text-sm font-medium text-green-400 mb-2">Approve {approveIp}</h4>
          <div className="flex gap-3 items-end">
            <div>
              <label className="text-xs text-immich-muted block mb-1">Access Level</label>
              <select value={approveLevel} onChange={(e) => setApproveLevel(e.target.value)}
                className="px-2 py-1 bg-immich-surface border border-immich-border rounded text-sm text-immich-text">
                <option value="user">User (Photo Curator only)</option>
                <option value="admin">Admin (All services)</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-immich-muted block mb-1">Duration</label>
              <select value={approveDuration} onChange={(e) => setApproveDuration(e.target.value)}
                className="px-2 py-1 bg-immich-surface border border-immich-border rounded text-sm text-immich-text">
                {DURATION_OPTIONS.map((d) => <option key={d} value={d}>{d}</option>)}
              </select>
            </div>
            <button onClick={() => {
              approveMut.mutate({ ip_address: approveIp, access_level: approveLevel, trust_duration: approveDuration })
              setApproveIp(null)
            }} className="px-3 py-1 bg-green-600 hover:bg-green-700 text-white text-sm rounded">Confirm</button>
            <button onClick={() => setApproveIp(null)}
              className="px-3 py-1 text-immich-muted hover:text-immich-text text-sm">Cancel</button>
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
  const ips = data?.ips || []

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-immich-muted text-left border-b border-immich-border">
            <th className="pb-2 pr-4">IP Address</th>
            <th className="pb-2 pr-4">Original User</th>
            <th className="pb-2 pr-4">Date Blacklisted</th>
            <th className="pb-2 pr-4">Blacklisted By</th>
            <th className="pb-2 pr-4">Reason</th>
            <th className="pb-2">Actions</th>
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
                <button onClick={() => unblockMut.mutate({ ip_address: ip.ip_address })}
                  className="text-xs text-yellow-400 hover:text-yellow-300">Unblock</button>
                <button onClick={() => deleteMut.mutate(ip.ip_address)}
                  className="text-xs text-red-400 hover:text-red-300">Delete</button>
              </td>
            </tr>
          ))}
          {ips.length === 0 && (
            <tr><td colSpan={6} className="py-4 text-center text-immich-muted">No blacklisted IPs</td></tr>
          )}
        </tbody>
      </table>
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
        <input placeholder="Filter by IP" onChange={(e) => setFilters(f => ({ ...f, ip: e.target.value || undefined }))}
          className="px-2 py-1 bg-immich-bg border border-immich-border rounded text-sm text-immich-text w-40" />
        <select onChange={(e) => setFilters(f => ({ ...f, service: e.target.value || undefined }))}
          className="px-2 py-1 bg-immich-bg border border-immich-border rounded text-sm text-immich-text">
          <option value="">All services</option>
          <option value="server-manager">server-manager</option>
          <option value="photo-curator">photo-curator</option>
          <option value="ssh">ssh</option>
        </select>
        <select onChange={(e) => setFilters(f => ({ ...f, action: e.target.value || undefined }))}
          className="px-2 py-1 bg-immich-bg border border-immich-border rounded text-sm text-immich-text">
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
        <div className="overflow-x-auto max-h-96 overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-immich-surface">
              <tr className="text-immich-muted text-left border-b border-immich-border">
                <th className="pb-2 pr-4">Timestamp</th>
                <th className="pb-2 pr-4">IP Address</th>
                <th className="pb-2 pr-4">Service</th>
                <th className="pb-2 pr-4">Action</th>
                <th className="pb-2">User</th>
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
                      c.action === 'allowed' ? 'text-green-400' :
                      c.action === 'blocked' ? 'text-red-400' :
                      c.action === 'challenged' ? 'text-yellow-400' :
                      'text-orange-400'
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
        <ShieldCheckIcon className="w-5 h-5 text-blue-400" />
        <h2 className="text-lg font-semibold">IP Security</h2>
      </div>

      <div className="flex gap-1 mb-4 border-b border-immich-border">
        {TABS.map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 text-sm transition-colors border-b-2 -mb-px ${
              activeTab === tab
                ? 'text-blue-400 border-blue-400'
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
