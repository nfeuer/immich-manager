import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '../utils/api'
import { TrashIcon } from '@heroicons/react/24/outline'

function DuplicateCard({ group, onDelete }) {
  const [keepId, setKeepId] = useState(group.assets[0]?.id)

  return (
    <div className="bg-immich-surface border border-immich-border rounded-xl p-4">
      <div className="flex gap-3 mb-3">
        {group.assets.map(asset => (
          <button
            key={asset.id}
            onClick={() => setKeepId(asset.id)}
            className={`flex-1 rounded-lg overflow-hidden ring-2 transition-all ${
              keepId === asset.id ? 'ring-immich-primary' : 'ring-transparent opacity-60 hover:opacity-90'
            }`}
          >
            <img src={`/api/thumbnail/${asset.id}`} alt="" className="w-full aspect-square object-cover" />
          </button>
        ))}
      </div>
      <div className="flex items-center justify-between">
        <p className="text-immich-muted text-xs">{group.assets.length} duplicates · click to select keep</p>
        <button
          onClick={() => onDelete(group.id, keepId)}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-red-700 text-white text-xs font-medium rounded-lg hover:bg-red-600"
        >
          <TrashIcon className="w-3.5 h-3.5" />
          Delete others
        </button>
      </div>
    </div>
  )
}

export default function Duplicates({ onAuthError }) {
  const queryClient = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['duplicates'],
    queryFn: () => apiFetch('/api/duplicates'),
  })

  const deleteMutation = useMutation({
    mutationFn: ({ groupId, keepId }) =>
      apiFetch(`/api/duplicates/${groupId}/resolve`, {
        method: 'POST',
        body: JSON.stringify({ keep_asset_id: keepId }),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['duplicates'] }),
  })

  const groups = data?.groups ?? []

  return (
    <div className="p-6">
      <h1 className="text-immich-text text-2xl font-semibold mb-6">Duplicates</h1>
      {isLoading ? (
        <p className="text-immich-muted">Loading…</p>
      ) : groups.length === 0 ? (
        <div className="text-center py-16 text-immich-muted">No duplicates found.</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {groups.map(group => (
            <DuplicateCard
              key={group.id}
              group={group}
              onDelete={(groupId, keepId) => deleteMutation.mutate({ groupId, keepId })}
            />
          ))}
        </div>
      )}
    </div>
  )
}
