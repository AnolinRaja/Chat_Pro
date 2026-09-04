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

let isRefreshing = false
let failedQueue = []

const processQueue = (error, token = null) => {
  failedQueue.forEach((prom) => {
    if (error) {
      prom.reject(error)
    } else {
      prom.resolve(token)
    }
  })
  failedQueue = []
}

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
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject })
        })
          .then((token) => {
            originalRequest.headers.Authorization = `Bearer ${token}`
            return api(originalRequest)
          })
          .catch((err) => Promise.reject(err))
      }

      originalRequest._retry = true
      isRefreshing = true

      try {
        const response = await api.post('/auth/refresh')
        const { access_token } = response.data

        setAccessToken(access_token)

        processQueue(null, access_token)
        isRefreshing = false

        originalRequest.headers.Authorization = `Bearer ${access_token}`
        return api(originalRequest)
      } catch (refreshError) {
        processQueue(refreshError, null)
        isRefreshing = false

        clearAccessToken()
        window.dispatchEvent(new Event('auth:logout'))
        return Promise.reject(refreshError)
      }
    }

    return Promise.reject(error)
  }
)

export default api
