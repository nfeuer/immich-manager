/**
 * Fetch wrapper that throws a structured AuthError on 401,
 * or a plain Error on other non-OK responses.
 */
export class AuthError extends Error {
  constructor(loginUrl) {
    super('Not authenticated')
    this.name = 'AuthError'
    this.loginUrl = loginUrl
  }
}

export async function apiFetch(path, options = {}) {
  const resp = await fetch(path, {
    credentials: 'include',
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
  })

  if (resp.status === 401) {
    let loginUrl = null
    try {
      const body = await resp.json()
      loginUrl = body?.detail?.login_url ?? null
    } catch (_) {}
    throw new AuthError(loginUrl)
  }

  if (!resp.ok) {
    throw new Error(`API error ${resp.status}: ${resp.statusText}`)
  }

  return resp.json()
}
