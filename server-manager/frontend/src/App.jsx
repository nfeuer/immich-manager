import React from 'react'
import Header from './components/Header.jsx'
import SystemStatusCard from './components/SystemStatusCard.jsx'
import ImmichStatusCard from './components/ImmichStatusCard.jsx'
import AlertsPanel from './components/AlertsPanel.jsx'
import DiskHealthCard from './components/DiskHealthCard.jsx'
import BackupsCard from './components/BackupsCard.jsx'
import LogViewer from './components/LogViewer.jsx'

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-immich-bg flex items-center justify-center p-8">
          <div className="bg-immich-surface border border-red-800 rounded-2xl p-6 max-w-lg w-full">
            <h2 className="text-red-400 font-semibold mb-2">Something went wrong</h2>
            <pre className="text-immich-muted text-xs font-mono whitespace-pre-wrap">
              {this.state.error?.message}
            </pre>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}

export default function App() {
  return (
    <ErrorBoundary>
      <div className="min-h-screen bg-immich-bg text-immich-text">
        <div className="max-w-[1400px] mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <Header />
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-5 mb-6">
            <SystemStatusCard />
            <ImmichStatusCard />
            <DiskHealthCard />
            <BackupsCard />
          </div>
          <AlertsPanel />
          <LogViewer />
        </div>
      </div>
    </ErrorBoundary>
  )
}
