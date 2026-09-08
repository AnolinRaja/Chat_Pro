import axios from 'axios'

let inMemoryAccessToken = null

export function setAccessToken(token) {
  inMemoryAccessToken = token || null
}

export function getAccessToken() {
  return inMemoryAccessToken
}

export function clearAccessToken() {
  inMemoryAccessToken = null
}

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,
})

api.interceptors.request.use((config) => {
  const token = getAccessToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

const AUTH_BYPASS_URLS = new Set([
  '/auth/refresh',
  '/auth/login',
  '/auth/login/2sv',
  '/auth/login/verify',
  '/auth/login/resend',
  '/auth/register',
  '/auth/register/verify',
  '/auth/register/resend',
  '/auth/forgot-password/request',
  '/auth/forgot-password/verify',
  '/auth/forgot-password/reset',
])

function isAuthBypassUrl(url) {
  if (!url) return false
  const cleanUrl = url.split('?')[0]
  return AUTH_BYPASS_URLS.has(cleanUrl)
}

// ---------------------------------------------------------------------------
// Single-flight refresh: guarantees at most ONE in-flight POST /auth/refresh
// regardless of how many consumers call this concurrently.
// ---------------------------------------------------------------------------
let _refreshPromise = null

/**
 * Returns a Promise that resolves to the refresh response data
 * ({ access_token, user? }).  If a refresh is already in flight, all callers
 * share the same Promise.  On success the in-memory access token is set
 * automatically.  On failure the access token is cleared and the error is
 * re-thrown so each caller can handle it independently.
 */
export function singleFlightRefresh() {
  if (_refreshPromise) return _refreshPromise

  _refreshPromise = api
    .post('/auth/refresh')
    .then((response) => {
      const data = response.data
      if (data?.access_token) {
        setAccessToken(data.access_token)
      }
      return data
    })
    .catch((error) => {
      clearAccessToken()
      throw error
    })
    .finally(() => {
      _refreshPromise = null
    })

  return _refreshPromise
}

// ---------------------------------------------------------------------------
// 401 interceptor — uses singleFlightRefresh() so that retried requests
// share the same single-flight guarantee as startup refresh.
// ---------------------------------------------------------------------------
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config

    if (
      error.response &&
      error.response.status === 401 &&
      originalRequest &&
      !originalRequest._retry &&
      !isAuthBypassUrl(originalRequest.url)
    ) {
      originalRequest._retry = true

      try {
        const data = await singleFlightRefresh()
        if (!originalRequest.headers) {
          originalRequest.headers = {}
        }
        originalRequest.headers.Authorization = `Bearer ${data.access_token}`
        return api(originalRequest)
      } catch (refreshError) {
        if (typeof window !== 'undefined') {
          window.dispatchEvent(new Event('auth:logout'))
        }
        return Promise.reject(refreshError)
      }
    }

    return Promise.reject(error)
  }
)

export default api
