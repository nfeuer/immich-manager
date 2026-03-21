import { useState, useEffect } from 'react'
import { useLastRefreshed } from '../hooks/useDashboard.js'

function ImmichLogoIcon() {
  return (
    <svg viewBox="0 0 32 32" className="w-7 h-7" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect width="32" height="32" rx="8" fill="#4250af"/>
      <path d="M8 22L16 10L24 22" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
      <circle cx="16" cy="10" r="2" fill="white"/>
    </svg>
  )
}

function formatSecondsAgo(ms) {
  if (!ms) return 'never'
  const seconds = Math.floor((Date.now() - ms) / 1000)
  if (seconds < 5) return 'just now'
  if (seconds < 60) return `${seconds}s ago`
  return `${Math.floor(seconds / 60)}m ago`
}

export default function Header() {
  const lastRefreshed = useLastRefreshed()
  const [label, setLabel] = useState(formatSecondsAgo(lastRefreshed))

  useEffect(() => {
    const id = setInterval(() => setLabel(formatSecondsAgo(lastRefreshed)), 1000)
    return () => clearInterval(id)
  }, [lastRefreshed])

  return (
    <header className="bg-immich-surface border border-immich-border rounded-2xl px-6 py-4 mb-6 flex items-center justify-between">
      <div className="flex items-center gap-3">
        <ImmichLogoIcon />
        <div>
          <h1 className="text-lg font-semibold text-immich-text leading-none">Server Manager</h1>
          <p className="text-xs text-immich-muted mt-0.5">Monitoring · Backups · Health</p>
        </div>
      </div>
      <span className="text-xs text-immich-muted">Updated {label}</span>
    </header>
  )
}
