// server-manager/frontend/src/pages/ChallengePage.jsx
import { useState, useEffect, useCallback } from 'react'
import { ShieldExclamationIcon, EnvelopeIcon } from '@heroicons/react/24/outline'

export default function ChallengePage() {
  const [email, setEmail] = useState('')
  const [submitted, setSubmitted] = useState(false)
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [ipStatus, setIpStatus] = useState(null)
  const [clientIp, setClientIp] = useState('')

  const checkStatus = useCallback(async () => {
    try {
      const resp = await fetch('/api/ip-gate/status')
      const data = await resp.json()
      setIpStatus(data.status)
      setClientIp(data.ip || '')
      if (data.status === 'trusted') {
        window.location.href = '/'
      }
    } catch {
      // ignore
    }
  }, [])

  useEffect(() => {
    checkStatus()
    const interval = setInterval(checkStatus, 5000)
    return () => clearInterval(interval)
  }, [checkStatus])

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setSubmitting(true)

    try {
      const resp = await fetch('/api/ip-gate/challenge', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
      })
      if (resp.ok) {
        setSubmitted(true)
      } else {
        const data = await resp.json()
        setError(data.detail || 'Failed to submit')
      }
    } catch (err) {
      setError('Network error. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen bg-immich-bg flex items-center justify-center p-4">
      <div className="bg-immich-surface border border-immich-border rounded-2xl p-8 max-w-md w-full">
        <div className="flex items-center gap-3 mb-6">
          <ShieldExclamationIcon className="w-8 h-8 text-yellow-400" />
          <h1 className="text-xl font-semibold text-immich-text">
            IP Verification Required
          </h1>
        </div>

        <p className="text-immich-muted text-sm mb-2">
          Your IP address <span className="font-mono text-immich-text">{clientIp}</span> has
          not been verified.
        </p>

        {!submitted ? (
          <form onSubmit={handleSubmit} className="mt-6">
            <label className="block text-sm text-immich-muted mb-2">
              Enter your email to receive a verification link:
            </label>
            <div className="flex gap-2">
              <div className="relative flex-1">
                <EnvelopeIcon className="w-5 h-5 text-immich-muted absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  required
                  className="w-full pl-10 pr-3 py-2 bg-immich-bg border border-immich-border rounded-lg
                             text-immich-text placeholder-immich-muted/50 text-sm
                             focus:outline-none focus:border-blue-500"
                />
              </div>
              <button
                type="submit"
                disabled={submitting}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50
                           text-white text-sm font-medium rounded-lg transition-colors"
              >
                {submitting ? 'Sending...' : 'Verify'}
              </button>
            </div>
            {error && (
              <p className="mt-2 text-red-400 text-sm">{error}</p>
            )}
          </form>
        ) : (
          <div className="mt-6">
            <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-4">
              <p className="text-blue-300 text-sm">
                A verification email has been sent if the account exists. Please check
                your email and click the approval link.
              </p>
            </div>
            <button
              onClick={checkStatus}
              className="mt-4 w-full px-4 py-2 bg-immich-bg border border-immich-border
                         hover:border-blue-500 text-immich-text text-sm rounded-lg transition-colors"
            >
              Refresh Status
            </button>
            {ipStatus === 'pending' && (
              <p className="mt-2 text-immich-muted text-xs text-center">
                Status: waiting for verification...
              </p>
            )}
          </div>
        )}

        <p className="mt-6 text-immich-muted text-xs">
          If this wasn't you, ignore this page. Contact your administrator if you
          believe this is an error.
        </p>
      </div>
    </div>
  )
}
