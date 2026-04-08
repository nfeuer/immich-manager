import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { useAuth } from './hooks/useAuth'
import { AuthError } from './utils/api'
import ErrorBoundary from './components/ErrorBoundary'
import Layout from './components/Layout'
import Login from './pages/Login'
import AlbumCurator from './pages/AlbumCurator'
import Import from './pages/Import'
import Duplicates from './pages/Duplicates'
import Events from './pages/Events'
import Analytics from './pages/Analytics'
import Preferences from './pages/Preferences'
import { useYearProgress } from './hooks/useYearProgress'

function AppInner() {
  const { loginUrl, onAuthError } = useAuth()
  const queryClient = useQueryClient()
  const currentYear = new Date().getFullYear()
  const { data: yearProgress } = useYearProgress(currentYear)

  // Wire auth error handler into react-query global
  useEffect(() => {
    const unsubscribe = queryClient.getQueryCache().subscribe((event) => {
      // TanStack Query v5: errors live at event.query.state.error, not event.error
      const error = event?.query?.state?.error
      if (error instanceof AuthError) {
        onAuthError(error)
      }
    })
    return unsubscribe
  }, [queryClient, onAuthError])

  if (loginUrl !== null) {
    return <Login loginUrl={loginUrl} />
  }

  const uncuratedCount = yearProgress
    ? Object.values(yearProgress).filter((v) => !v).length
    : 0

  return (
    <Routes>
      <Route element={<Layout uncuratedCount={uncuratedCount} />}>
        <Route index element={<AlbumCurator onAuthError={onAuthError} />} />
        <Route path="import" element={<Import onAuthError={onAuthError} />} />
        <Route path="duplicates" element={<Duplicates onAuthError={onAuthError} />} />
        <Route path="events" element={<Events onAuthError={onAuthError} />} />
        <Route path="analytics" element={<Analytics onAuthError={onAuthError} />} />
        <Route path="preferences" element={<Preferences onAuthError={onAuthError} />} />
      </Route>
    </Routes>
  )
}

export default function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <AppInner />
      </BrowserRouter>
    </ErrorBoundary>
  )
}
