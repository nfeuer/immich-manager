export default function CurationFooter({ selectedCount, recommendedCount, onSave, onReset, isSaving }) {
  return (
    <div
      data-testid="curation-footer"
      className="fixed bottom-16 md:bottom-0 left-0 md:left-[220px] right-0 bg-immich-surface border-t border-immich-border px-4 py-3 flex items-center justify-between z-20"
    >
      <span className="text-immich-text text-sm">
        <span className="font-semibold">{selectedCount} selected</span>
        {recommendedCount !== null && (
          <span className="text-immich-muted ml-2">· Recommended: {recommendedCount}</span>
        )}
      </span>
      <div className="flex gap-2">
        <button
          type="button"
          onClick={onReset}
          className="px-4 py-2 bg-immich-surface text-immich-text font-medium rounded-lg border border-immich-border hover:bg-immich-border transition-colors text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-primary"
        >
          Reset
        </button>
        <button
          type="button"
          onClick={onSave}
          disabled={isSaving || selectedCount === 0}
          className="px-4 py-2 bg-immich-primary text-white font-medium rounded-lg hover:opacity-90 transition-opacity disabled:opacity-50 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-primary"
        >
          {isSaving ? 'Saving…' : 'Save Album'}
        </button>
      </div>
    </div>
  )
}
