import { useState } from 'react'
import { ChevronLeftIcon, ChevronRightIcon, SparklesIcon } from '@heroicons/react/24/outline'
import { useCurator } from '../hooks/useCurator'
import { useYearProgress } from '../hooks/useYearProgress'
import YearTracker from '../components/YearTracker'
import PhotoGrid from '../components/PhotoGrid'
import CurationFooter from '../components/CurationFooter'

const MONTH_NAMES = ['January','February','March','April','May','June',
                     'July','August','September','October','November','December']

export default function AlbumCurator() {
  const now = new Date()
  const [year, setYear] = useState(now.getFullYear())
  const [month, setMonth] = useState(now.getMonth() + 1)

  const {
    photos, isLoading, rawTotal, scoredTotal, analysisComplete,
    selected, curated, togglePhoto, aiCurate, isCurating, saveAlbum, isSaving, resetCuration,
    recommendedCount,
  } = useCurator(year, month)

  const { data: yearProgress } = useYearProgress(year)

  const prevMonth = () => {
    if (month === 1) { setMonth(12); setYear(y => y - 1) }
    else setMonth(m => m - 1)
  }
  const nextMonth = () => {
    if (month === 12) { setMonth(1); setYear(y => y + 1) }
    else setMonth(m => m + 1)
  }

  const analysisProgress = rawTotal > 0 ? Math.round((scoredTotal / rawTotal) * 100) : 0

  return (
    <div className="min-h-screen">
      {/* Header */}
      <div className="sticky top-0 bg-immich-bg/95 backdrop-blur border-b border-immich-border px-4 py-3 z-10">
        {/* Month switcher */}
        <div className="flex items-center gap-3 mb-3">
          <button type="button" onClick={prevMonth} aria-label="Previous month" className="p-1.5 rounded-lg hover:bg-immich-surface transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-primary">
            <ChevronLeftIcon className="w-5 h-5 text-immich-muted" />
          </button>
          <span data-testid="month-label" className="text-immich-text font-semibold text-lg min-w-[160px] text-center">
            {MONTH_NAMES[month - 1]} {year}
          </span>
          <button type="button" onClick={nextMonth} aria-label="Next month" className="p-1.5 rounded-lg hover:bg-immich-surface transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-primary">
            <ChevronRightIcon className="w-5 h-5 text-immich-muted" />
          </button>
          <div className="ml-auto">
            <button
              type="button"
              onClick={() => aiCurate()}
              disabled={rawTotal === 0 || isCurating}
              className="flex items-center gap-2 px-4 py-2 bg-immich-primary text-white font-medium rounded-lg hover:opacity-90 transition-opacity disabled:opacity-40 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-primary"
            >
              <SparklesIcon className="w-4 h-4" />
              {isCurating ? 'Curating…' : 'AI Curate'}
            </button>
          </div>
        </div>

        {/* Year tracker */}
        {yearProgress && (
          <YearTracker
            year={year}
            progress={yearProgress}
            currentMonth={month}
            onSelect={(m) => setMonth(m)}
          />
        )}

        {/* Analysis progress bar */}
        {!analysisComplete && rawTotal > 0 && (
          <div className="mt-2">
            <div className="flex justify-between text-xs text-immich-muted mb-1">
              <span>Analyzing photos…</span>
              <span>{scoredTotal} / {rawTotal}</span>
            </div>
            <div className="h-1 bg-immich-border rounded-full overflow-hidden">
              <div
                className="h-full bg-immich-primary transition-all"
                style={{ width: `${analysisProgress}%` }}
              />
            </div>
          </div>
        )}
      </div>

      {/* Photo grid */}
      {isLoading ? (
        <div className="flex items-center justify-center h-64 text-immich-muted">Loading photos…</div>
      ) : photos.length === 0 ? (
        <div className="flex items-center justify-center h-64 text-immich-muted">No photos found for this month.</div>
      ) : (
        <PhotoGrid photos={photos} selected={selected} onToggle={togglePhoto} />
      )}

      {/* Curation footer */}
      {curated && (
        <CurationFooter
          selectedCount={selected.size}
          recommendedCount={recommendedCount}
          onSave={saveAlbum}
          onReset={resetCuration}
          isSaving={isSaving}
        />
      )}
    </div>
  )
}
