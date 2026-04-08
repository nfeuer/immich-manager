const MONTH_LABELS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']

export default function YearTracker({ year, progress = {}, currentMonth, onSelect }) {
  return (
    <div className="flex gap-1.5 flex-wrap">
      {MONTH_LABELS.map((label, idx) => {
        const month = idx + 1
        const curated = !!progress[month]
        const isCurrent = month === currentMonth
        return (
          <button
            key={month}
            data-testid="month-pill"
            data-curated={curated}
            onClick={() => onSelect(month)}
            className={`px-2.5 py-1 rounded-full text-xs font-medium transition-colors ring-1 ${
              curated
                ? 'bg-immich-success-muted text-immich-success ring-immich-success-border'
                : 'bg-immich-surface text-immich-muted ring-immich-border'
            } ${isCurrent ? 'ring-2 ring-immich-primary' : ''} hover:opacity-80 focus-visible:ring-2 focus-visible:ring-immich-primary`}
          >
            {label}
          </button>
        )
      })}
    </div>
  )
}
