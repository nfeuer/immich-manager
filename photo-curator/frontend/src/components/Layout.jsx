import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'
import BottomTabBar from './BottomTabBar'

export default function Layout({ uncuratedCount = 0 }) {
  return (
    <div className="min-h-screen bg-immich-bg">
      <Sidebar uncuratedCount={uncuratedCount} />
      {/* Main content — offset for sidebar on desktop, padding-bottom for bottom tabs on mobile */}
      <main className="md:ml-[220px] pb-16 md:pb-0">
        <Outlet />
      </main>
      <BottomTabBar />
    </div>
  )
}
