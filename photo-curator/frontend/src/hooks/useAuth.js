import { useState, useCallback } from 'react'
import { AuthError } from '../utils/api'

/**
 * Tracks auth state. When any query throws an AuthError,
 * call onAuthError(error) to capture the login URL and show the Login page.
 */
export function useAuth() {
  const [loginUrl, setLoginUrl] = useState(null)

  const onAuthError = useCallback((error) => {
    if (error instanceof AuthError) {
      setLoginUrl(error.loginUrl)
    }
  }, [])

  const clearAuthError = useCallback(() => setLoginUrl(null), [])

  return { loginUrl, onAuthError, clearAuthError }
}
