import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '../utils/api'
import { PlusIcon } from '@heroicons/react/24/outline'

export default function Events() {
  const queryClient = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['events'],
    queryFn: () => apiFetch('/api/events'),
  })

  const createMutation = useMutation({
    mutationFn: ({ eventId, albumName }) =>
      apiFetch(`/api/events/${eventId}/album`, {
        method: 'POST',
        body: JSON.stringify({ album_name: albumName }),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['events'] }),
  })

  const events = data?.events ?? []

  return (
    <div className="p-6">
      <h1 className="text-immich-text text-2xl font-semibold mb-6">Events & Trips</h1>
      {isLoading ? (
        <p className="text-immich-muted">Detecting events…</p>
      ) : events.length === 0 ? (
        <div className="text-center py-16 text-immich-muted">No events detected yet.</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {events.map(event => (
            <div key={event.id} className="bg-immich-surface border border-immich-border rounded-xl overflow-hidden">
              {/* Thumbnail strip */}
              <div className="flex h-24 gap-0.5">
                {(event.thumbnails ?? []).slice(0, 3).map((url, i) => (
                  <img key={i} src={url} alt="" className="flex-1 object-cover" />
                ))}
              </div>
              <div className="p-3">
                <p className="text-immich-text font-medium text-sm">{event.title ?? 'Untitled event'}</p>
                <p className="text-immich-muted text-xs mt-0.5">{event.date_range} · {event.photo_count} photos</p>
                <button
                  type="button"
                  onClick={() => createMutation.mutate({ eventId: event.id, albumName: event.title })}
                  className="mt-3 flex items-center gap-1.5 px-3 py-1.5 bg-immich-primary text-white text-xs font-medium rounded-lg hover:opacity-90 focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-primary"
                >
                  <PlusIcon className="w-3.5 h-3.5" />
                  Create Album
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
