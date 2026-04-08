export default function PhotoGrid({ photos, selected, onToggle }) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-2 p-4">
      {photos.map(photo => {
        const isSelected = selected.has(photo.asset_id)
        return (
          <button
            type="button"
            key={photo.asset_id}
            data-testid={`photo-${photo.asset_id}`}
            onClick={() => onToggle(photo.asset_id)}
            aria-pressed={isSelected}
            className={`relative aspect-square rounded-lg overflow-hidden ring-2 transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-primary ${
              isSelected ? 'ring-immich-primary' : 'ring-transparent opacity-70 hover:opacity-100'
            }`}
          >
            <img
              src={photo.thumbnail_url}
              alt=""
              className="w-full h-full object-cover"
              loading="lazy"
            />
            {isSelected && (
              <div className="absolute inset-0 bg-immich-primary/20 flex items-end justify-end p-1">
                <div className="w-5 h-5 rounded-full bg-immich-primary flex items-center justify-center">
                  <svg className="w-3 h-3 text-white" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                  </svg>
                </div>
              </div>
            )}
          </button>
        )
      })}
    </div>
  )
}
