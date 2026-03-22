import { useState } from 'react'
import { CheckIcon } from '@heroicons/react/24/solid'

const SOURCES = [
  { id: 'google', label: 'Google Photos', desc: 'Import from a Google Takeout export' },
  { id: 'apple', label: 'Apple Photos', desc: 'Import from an Apple Photos export' },
  { id: 'icloud', label: 'iCloud', desc: 'Import from iCloud Drive' },
]

const STEPS = ['Choose source', 'Configure', 'Preview', 'Import']

export default function Import({ onAuthError }) {
  const [step, setStep] = useState(0)
  const [source, setSource] = useState(null)
  const [path, setPath] = useState('')

  return (
    <div className="p-6 max-w-2xl mx-auto">
      <h1 className="text-immich-text text-2xl font-semibold mb-6">Import Photos</h1>

      {/* Step indicator */}
      <div className="flex items-center gap-2 mb-8">
        {STEPS.map((label, i) => (
          <div key={label} className="flex items-center gap-2 flex-1">
            <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 ${
              i < step ? 'bg-green-600 text-white' :
              i === step ? 'bg-immich-primary text-white' :
              'bg-immich-surface text-immich-muted border border-immich-border'
            }`}>
              {i < step ? <CheckIcon className="w-4 h-4" /> : i + 1}
            </div>
            <span className={`text-xs ${i === step ? 'text-immich-text' : 'text-immich-muted'} hidden sm:block`}>{label}</span>
            {i < STEPS.length - 1 && <div className="flex-1 h-px bg-immich-border" />}
          </div>
        ))}
      </div>

      {/* Step 0: Choose source */}
      {step === 0 && (
        <div className="space-y-3">
          {SOURCES.map(s => (
            <button
              key={s.id}
              onClick={() => setSource(s.id)}
              className={`w-full text-left p-4 rounded-xl border transition-colors ${
                source === s.id
                  ? 'border-immich-primary bg-immich-primary/10'
                  : 'border-immich-border bg-immich-surface hover:border-immich-muted'
              }`}
            >
              <p className="text-immich-text font-medium">{s.label}</p>
              <p className="text-immich-muted text-sm mt-0.5">{s.desc}</p>
            </button>
          ))}
          <button
            disabled={!source}
            onClick={() => setStep(1)}
            className="mt-4 px-4 py-2 bg-immich-primary text-white font-medium rounded-lg disabled:opacity-40"
          >
            Next
          </button>
        </div>
      )}

      {/* Step 1: Configure */}
      {step === 1 && (
        <div className="space-y-4">
          <label className="block">
            <span className="text-immich-text text-sm font-medium">Export path or file</span>
            <input
              type="text"
              value={path}
              onChange={e => setPath(e.target.value)}
              placeholder="/path/to/export"
              className="mt-1 w-full px-3 py-2 bg-immich-surface border border-immich-border rounded-lg text-immich-text placeholder-immich-muted text-sm focus:outline-none focus:border-immich-primary"
            />
          </label>
          <div className="flex gap-2">
            <button onClick={() => setStep(0)} className="px-4 py-2 bg-immich-surface text-immich-text border border-immich-border rounded-lg text-sm">Back</button>
            <button disabled={!path} onClick={() => setStep(2)} className="px-4 py-2 bg-immich-primary text-white font-medium rounded-lg disabled:opacity-40 text-sm">Preview</button>
          </div>
        </div>
      )}

      {/* Step 2: Preview placeholder */}
      {step === 2 && (
        <div className="space-y-4">
          <div className="p-4 bg-immich-surface rounded-xl border border-immich-border">
            <p className="text-immich-muted text-sm">Preview scan would appear here.</p>
            <p className="text-immich-text text-sm mt-1">Source: <strong>{source}</strong> — Path: <strong>{path}</strong></p>
          </div>
          <div className="flex gap-2">
            <button onClick={() => setStep(1)} className="px-4 py-2 bg-immich-surface text-immich-text border border-immich-border rounded-lg text-sm">Back</button>
            <button onClick={() => setStep(3)} className="px-4 py-2 bg-immich-primary text-white font-medium rounded-lg text-sm">Start Import</button>
          </div>
        </div>
      )}

      {/* Step 3: Import progress placeholder */}
      {step === 3 && (
        <div className="p-4 bg-immich-surface rounded-xl border border-immich-border">
          <p className="text-immich-text font-medium">Import in progress…</p>
          <div className="h-2 bg-immich-border rounded-full mt-3 overflow-hidden">
            <div className="h-full bg-immich-primary w-1/3 animate-pulse" />
          </div>
        </div>
      )}
    </div>
  )
}
