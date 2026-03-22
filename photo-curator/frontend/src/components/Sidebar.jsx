import { NavLink } from 'react-router-dom'
import {
  PhotoIcon,
  ArrowUpTrayIcon,
  DocumentDuplicateIcon,
  MapIcon,
  ChartBarIcon,
  Cog6ToothIcon,
} from '@heroicons/react/24/outline'

const NAV_ITEMS = [
  { to: '/',            label: 'AI Album Curator', Icon: PhotoIcon,             key: 'curator' },
  { to: '/import',      label: 'Import',            Icon: ArrowUpTrayIcon,       key: 'import' },
  { to: '/duplicates',  label: 'Duplicates',        Icon: DocumentDuplicateIcon, key: 'duplicates' },
  { to: '/events',      label: 'Events & Trips',    Icon: MapIcon,               key: 'events' },
  { to: '/analytics',   label: 'Analytics',         Icon: ChartBarIcon,          key: 'analytics' },
  { to: '/preferences', label: 'Preferences',       Icon: Cog6ToothIcon,         key: 'preferences' },
]

export default function Sidebar({ uncuratedCount = 0 }) {
  return (
    <aside className="hidden md:flex flex-col w-[220px] bg-immich-surface border-r border-immich-border h-screen fixed left-0 top-0">
      {/* Logo + Title */}
      <div className="flex items-center gap-3 px-4 py-5 border-b border-immich-border">
        <div className="w-8 h-8 rounded-full bg-immich-primary flex items-center justify-center flex-shrink-0">
          <span className="text-white text-sm font-bold">I</span>
        </div>
        <span className="text-immich-text font-semibold text-sm">Photo Curator</span>
      </div>

      {/* Nav */}
      <nav className="flex-1 py-3 overflow-y-auto">
        {NAV_ITEMS.map(({ to, label, Icon, key }) => (
          <NavLink
            key={key}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 px-4 py-2.5 text-sm font-medium rounded-lg mx-2 mb-0.5 transition-colors ${
                isActive
                  ? 'bg-immich-primary/20 text-immich-primary'
                  : 'text-immich-muted hover:text-immich-text hover:bg-immich-border/40'
              }`
            }
          >
            <Icon className="w-5 h-5 flex-shrink-0" />
            <span className="flex-1">{label}</span>
            {key === 'curator' && uncuratedCount > 0 && (
              <span
                data-testid="curator-badge"
                className="bg-immich-primary text-white text-xs font-bold px-1.5 py-0.5 rounded-full min-w-[1.25rem] text-center"
              >
                {uncuratedCount}
              </span>
            )}
          </NavLink>
        ))}
      </nav>
    </aside>
  )
}
