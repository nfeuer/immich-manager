import React from 'react'
import ChallengePage from './pages/ChallengePage.jsx'
import Header from './components/Header.jsx'
import SystemStatusCard from './components/SystemStatusCard.jsx'
import ImmichStatusCard from './components/ImmichStatusCard.jsx'
import AlertsPanel from './components/AlertsPanel.jsx'
import DiskHealthCard from './components/DiskHealthCard.jsx'
import BackupsCard from './components/BackupsCard.jsx'
import LogViewer from './components/LogViewer.jsx'
import ServiceControls from './components/ServiceControls.jsx'
import UpdateManagement from './components/UpdateManagement.jsx'
import DiscordConfig from './components/DiscordConfig.jsx'
import IPManagement from './components/IPManagement.jsx'
import ErrorBoundary from './components/ErrorBoundary'

export default function App() {
  if (window.location.pathname === '/ip-challenge') {
    return <ChallengePage />
  }

  return (
    <ErrorBoundary>
      <div className="min-h-screen bg-immich-bg text-immich-text">
        <main id="main" className="max-w-[1400px] mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <Header />
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-5 mb-6">
            <SystemStatusCard />
            <ImmichStatusCard />
            <DiskHealthCard />
            <BackupsCard />
          </div>
          <AlertsPanel />
          <LogViewer />
          <ServiceControls />
          <DiscordConfig />
          <UpdateManagement />
          <IPManagement />
        </main>
      </div>
    </ErrorBoundary>
  )
}
