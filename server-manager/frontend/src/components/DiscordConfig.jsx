import { useState, useEffect } from 'react'
import { ChatBubbleLeftRightIcon } from '@heroicons/react/24/outline'
import {
  useDiscordConfig, useUpdateDiscordConfig, useTestAlert, useTestDigest,
} from '../hooks/useDiscordConfig.js'

const DIGEST_SECTIONS = ['system', 'storage', 'backups', 'containers', 'alerts']

function Toggle({ enabled, onChange, label }) {
  return (
    <label className="flex items-center gap-2 cursor-pointer select-none">
      <button
        type="button"
        role="switch"
        aria-checked={enabled}
        onClick={() => onChange(!enabled)}
        className={`relative w-9 h-5 rounded-full transition-colors duration-200 ${enabled ? 'bg-immich-primary' : 'bg-immich-border'}`}
      >
        <span className={`absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full transition-transform duration-200 ${enabled ? 'translate-x-4' : ''}`} />
      </button>
      <span className="text-sm text-immich-text">{label}</span>
    </label>
  )
}

function Field({ label, htmlFor, children }) {
  return (
    <div className="space-y-1">
      <label htmlFor={htmlFor} className="block text-xs font-medium text-immich-muted">{label}</label>
      {children}
    </div>
  )
}

const inputClass = 'w-full px-3 py-2 bg-immich-bg border border-immich-border rounded-lg text-sm text-immich-text placeholder-immich-muted/50 focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-primary focus:border-immich-primary transition-colors'

export default function DiscordConfig() {
  const { data, isLoading, isError } = useDiscordConfig()
  const updateMut = useUpdateDiscordConfig()
  const testAlertMut = useTestAlert()
  const testDigestMut = useTestDigest()

  // Local form state
  const [discord, setDiscord] = useState({ enabled: false, webhook_url: '', bot_name: 'Immich Manager', server_name: '' })
  const [digest, setDigest] = useState({ enabled: false, schedule: '0 9 * * *', sections: ['system', 'storage', 'backups', 'containers', 'alerts'] })
  const [quietHours, setQuietHours] = useState({ enabled: true, start: '22:00', end: '08:00' })
  const [dirty, setDirty] = useState(false)
  const [saveMsg, setSaveMsg] = useState(null)

  // Sync from server
  useEffect(() => {
    if (data) {
      setDiscord(data.discord)
      setDigest(data.digest)
      setQuietHours(data.quiet_hours)
      setDirty(false)
    }
  }, [data])

  function updateDiscord(patch) {
    setDiscord((prev) => ({ ...prev, ...patch }))
    setDirty(true)
  }

  function updateDigest(patch) {
    setDigest((prev) => ({ ...prev, ...patch }))
    setDirty(true)
  }

  function updateQuietHours(patch) {
    setQuietHours((prev) => ({ ...prev, ...patch }))
    setDirty(true)
  }

  function toggleSection(section) {
    setDigest((prev) => {
      const sections = prev.sections.includes(section)
        ? prev.sections.filter((s) => s !== section)
        : [...prev.sections, section]
      return { ...prev, sections }
    })
    setDirty(true)
  }

  async function handleSave() {
    setSaveMsg(null)
    try {
      await updateMut.mutateAsync({ discord, digest, quiet_hours: quietHours })
      setDirty(false)
      setSaveMsg({ type: 'ok', text: 'Configuration saved.' })
    } catch (err) {
      setSaveMsg({ type: 'error', text: `Failed to save: ${err.message}` })
    }
    setTimeout(() => setSaveMsg(null), 4000)
  }

  if (isLoading) {
    return (
      <div className="bg-immich-surface border border-immich-border rounded-2xl p-5 mb-6">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-immich-muted mb-4 flex items-center gap-1.5">
          <ChatBubbleLeftRightIcon className="w-3.5 h-3.5" /> Discord Configuration
        </h2>
        <p className="text-immich-muted text-sm">Loading...</p>
      </div>
    )
  }

  if (isError) {
    return (
      <div className="bg-immich-surface border border-immich-border rounded-2xl p-5 mb-6">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-immich-muted mb-4 flex items-center gap-1.5">
          <ChatBubbleLeftRightIcon className="w-3.5 h-3.5" /> Discord Configuration
        </h2>
        <p className="text-immich-error text-sm">Failed to load Discord configuration.</p>
      </div>
    )
  }

  return (
    <div className="bg-immich-surface border border-immich-border rounded-2xl p-5 mb-6">
      <h2 className="text-xs font-semibold uppercase tracking-wider text-immich-muted mb-4 flex items-center gap-1.5">
        <ChatBubbleLeftRightIcon className="w-3.5 h-3.5" /> Discord Configuration
      </h2>

      <div className="space-y-6">
        {/* ── Discord Alerts ── */}
        <section>
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-immich-text">Discord Alerts</h3>
            <Toggle enabled={discord.enabled} onChange={(v) => updateDiscord({ enabled: v })} label="Enabled" />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Field label="Webhook URL" htmlFor="discord-webhook-url">
              <input
                id="discord-webhook-url"
                type="url"
                value={discord.webhook_url}
                onChange={(e) => updateDiscord({ webhook_url: e.target.value })}
                placeholder="https://discord.com/api/webhooks/..."
                className={inputClass}
              />
            </Field>
            <Field label="Bot Display Name" htmlFor="discord-bot-name">
              <input
                id="discord-bot-name"
                type="text"
                value={discord.bot_name}
                onChange={(e) => updateDiscord({ bot_name: e.target.value })}
                placeholder="Immich Manager"
                className={inputClass}
              />
            </Field>
            <Field label="Server Name (optional label)" htmlFor="discord-server-name">
              <input
                id="discord-server-name"
                type="text"
                value={discord.server_name}
                onChange={(e) => updateDiscord({ server_name: e.target.value })}
                placeholder="e.g. Home Server"
                className={inputClass}
              />
            </Field>
            <div className="flex items-end">
              <button
                type="button"
                onClick={() => testAlertMut.mutate()}
                disabled={!discord.enabled || !discord.webhook_url || testAlertMut.isPending}
                className="px-4 py-2 bg-immich-primary hover:bg-immich-primary-hover disabled:opacity-40 text-white rounded-lg text-sm font-medium transition-colors duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-primary"
              >
                {testAlertMut.isPending ? 'Sending...' : testAlertMut.isSuccess ? 'Sent!' : testAlertMut.isError ? 'Failed' : 'Test Alert'}
              </button>
            </div>
          </div>
        </section>

        <hr className="border-immich-border" />

        {/* ── Digest ── */}
        <section>
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-immich-text">Discord Digest</h3>
            <Toggle enabled={digest.enabled} onChange={(v) => updateDigest({ enabled: v })} label="Enabled" />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Field label="Schedule (cron expression)" htmlFor="digest-schedule">
              <input
                id="digest-schedule"
                type="text"
                value={digest.schedule}
                onChange={(e) => updateDigest({ schedule: e.target.value })}
                placeholder="0 9 * * *"
                className={inputClass}
              />
              <p className="text-xs text-immich-muted mt-1">Default: daily at 9 AM</p>
            </Field>
            <div className="flex items-end">
              <button
                type="button"
                onClick={() => testDigestMut.mutate()}
                disabled={!discord.enabled || !discord.webhook_url || testDigestMut.isPending}
                className="px-4 py-2 bg-immich-primary hover:bg-immich-primary-hover disabled:opacity-40 text-white rounded-lg text-sm font-medium transition-colors duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-primary"
              >
                {testDigestMut.isPending ? 'Sending...' : testDigestMut.isSuccess ? 'Sent!' : testDigestMut.isError ? 'Failed' : 'Test Digest'}
              </button>
            </div>
          </div>
          <div className="mt-3">
            <span className="block text-xs font-medium text-immich-muted mb-2">Sections to include</span>
            <div className="flex flex-wrap gap-3">
              {DIGEST_SECTIONS.map((sec) => (
                <label key={sec} className="flex items-center gap-1.5 cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={digest.sections.includes(sec)}
                    onChange={() => toggleSection(sec)}
                    className="w-3.5 h-3.5 rounded border-immich-border bg-immich-bg text-immich-primary focus:ring-immich-primary"
                  />
                  <span className="text-sm text-immich-text capitalize">{sec}</span>
                </label>
              ))}
            </div>
          </div>
        </section>

        <hr className="border-immich-border" />

        {/* ── Quiet Hours ── */}
        <section>
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-immich-text">Quiet Hours</h3>
            <Toggle enabled={quietHours.enabled} onChange={(v) => updateQuietHours({ enabled: v })} label="Enabled" />
          </div>
          <p className="text-xs text-immich-muted mb-3">Non-critical alerts are suppressed during quiet hours. Critical alerts always send.</p>
          <div className="grid grid-cols-2 gap-4 max-w-xs">
            <Field label="Start" htmlFor="quiet-hours-start">
              <input
                id="quiet-hours-start"
                type="time"
                value={quietHours.start}
                onChange={(e) => updateQuietHours({ start: e.target.value })}
                className={inputClass}
              />
            </Field>
            <Field label="End" htmlFor="quiet-hours-end">
              <input
                id="quiet-hours-end"
                type="time"
                value={quietHours.end}
                onChange={(e) => updateQuietHours({ end: e.target.value })}
                className={inputClass}
              />
            </Field>
          </div>
        </section>
      </div>

      {/* ── Save Bar ── */}
      <div className="mt-6 flex items-center gap-3">
        <button
          type="button"
          onClick={handleSave}
          disabled={!dirty || updateMut.isPending}
          className="px-5 py-2 bg-immich-primary hover:bg-immich-primary-hover disabled:opacity-40 text-white rounded-lg text-sm font-semibold transition-colors duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-primary"
        >
          {updateMut.isPending ? 'Saving...' : 'Save Changes'}
        </button>
        {saveMsg && (
          <span className={`text-sm ${saveMsg.type === 'ok' ? 'text-immich-success' : 'text-immich-error'}`}>
            {saveMsg.text}
          </span>
        )}
        {dirty && !saveMsg && (
          <span className="text-xs text-immich-muted">Unsaved changes</span>
        )}
      </div>
    </div>
  )
}
