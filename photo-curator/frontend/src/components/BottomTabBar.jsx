import { NavLink } from 'react-router-dom'
import {
  PhotoIcon,
  ArrowUpTrayIcon,
  DocumentDuplicateIcon,
  MapIcon,
  ChartBarIcon,
  Cog6ToothIcon,
} from '@heroicons/react/24/outline'

const TABS = [
  { to: '/',            Icon: PhotoIcon,             label: 'Curator' },
  { to: '/import',      Icon: ArrowUpTrayIcon,       label: 'Import' },
  { to: '/duplicates',  Icon: DocumentDuplicateIcon, label: 'Dupes' },
  { to: '/events',      Icon: MapIcon,               label: 'Events' },
  { to: '/analytics',   Icon: ChartBarIcon,          label: 'Analytics' },
  { to: '/preferences', Icon: Cog6ToothIcon,         label: 'Settings' },
]

export default function BottomTabBar() {
  return (
    <nav className="md:hidden fixed bottom-0 left-0 right-0 bg-immich-surface border-t border-immich-border flex z-10">
      {TABS.map(({ to, Icon, label }) => (
        <NavLink
          key={to}
          to={to}
          end={to === '/'}
          aria-label={label}
          className={({ isActive }) =>
            `flex-1 flex flex-col items-center py-2 gap-0.5 text-xs transition-colors ${
              isActive ? 'text-immich-primary' : 'text-immich-muted'
            }`
          }
        >
          <Icon className="w-5 h-5" />
          <span className="hidden min-[360px]:inline">{label}</span>
        </NavLink>
      ))}
    </nav>
  )
}
