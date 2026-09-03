import { useEffect, useState } from 'react'
import api, { TOKEN_STORAGE_KEY } from '../services/api.js'
import authContextValue from './authContextValue.js'

function getErrorMessage(error, fallback) {
  if (!error.response) return 'Unable to connect to the backend. Check the connection and try again.'
  const detail = error.response.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map((item) => item.msg).join(' ')
  if (error.response.status === 401) return 'Invalid credentials or verification code.'
  if (error.response.status === 409) return 'An account with that email already exists.'
  if (error.response.status === 429) return 'Too many requests. Please wait and try again.'
  return fallback
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [isLoading, setIsLoading] = useState(true)

  const clearSession = () => {
    localStorage.removeItem(TOKEN_STORAGE_KEY)
    setUser(null)
  }

  const refreshUser = async () => {
    const response = await api.get('/auth/me')
    setUser(response.data)
    return response.data
  }

  const login = async (credentials) => {
    try {
      const response = await api.post('/auth/login', credentials)
      if (response.data.access_token) {
        localStorage.setItem(TOKEN_STORAGE_KEY, response.data.access_token)
        await refreshUser()
      }
      return response.data
    } catch (error) {
      clearSession()
      throw new Error(getErrorMessage(error, 'Unable to sign in. Please try again.'), { cause: error })
    }
  }

  const verify2SV = async (two_factor_token, code) => {
    try {
      const response = await api.post('/auth/login/2sv', { two_factor_token, code })
      if (response.data.access_token) {
        localStorage.setItem(TOKEN_STORAGE_KEY, response.data.access_token)
        await refreshUser()
      }
      return response.data
    } catch (error) {
      clearSession()
      throw new Error(getErrorMessage(error, 'Invalid verification code or recovery code. Please try again.'), { cause: error })
    }
  }

  const verifyLogin = async (email, otp) => {
    try {
      const response = await api.post('/auth/login/verify', { email, otp })
      localStorage.setItem(TOKEN_STORAGE_KEY, response.data.access_token)
      await refreshUser()
      return response.data
    } catch (error) {
      clearSession()
      throw new Error(getErrorMessage(error, 'Unable to verify your sign in. Please try again.'), { cause: error })
    }
  }

  const register = async (details) => {
    try {
      const response = await api.post('/auth/register', details)
      return response.data
    } catch (error) {
      throw new Error(getErrorMessage(error, 'Unable to create your account. Please try again.'), { cause: error })
    }
  }

  const logout = async () => {
    try {
      await api.post('/auth/logout')
    } catch (error) {
      console.error('Failed to log out on backend:', error)
    } finally {
      clearSession()
    }
  }

  useEffect(() => {
    const handleAuthLogout = () => {
      clearSession()
    }
    window.addEventListener('auth:logout', handleAuthLogout)
    return () => window.removeEventListener('auth:logout', handleAuthLogout)
  }, [])

  useEffect(() => {
    const restoreSession = async () => {
      const token = localStorage.getItem(TOKEN_STORAGE_KEY)
      if (token) {
        try {
          await refreshUser()
        } catch (error) {
          if (error.response && error.response.status === 401) {
            try {
              const refreshRes = await api.post('/auth/refresh')
              const newAccessToken = refreshRes.data.access_token
              localStorage.setItem(TOKEN_STORAGE_KEY, newAccessToken)
              await refreshUser()
            } catch {
              clearSession()
            }
          } else {
            clearSession()
          }
        }
      } else {
        try {
          const refreshRes = await api.post('/auth/refresh')
          const newAccessToken = refreshRes.data.access_token
          localStorage.setItem(TOKEN_STORAGE_KEY, newAccessToken)
          await refreshUser()
        } catch {
          clearSession()
        }
      }
      setIsLoading(false)
    }
    restoreSession()
  }, [])

  return (
    <authContextValue.Provider value={{ user, isLoading, login, verify2SV, verifyLogin, register, logout, refreshUser }}>
      {children}
    </authContextValue.Provider>
  )
}
