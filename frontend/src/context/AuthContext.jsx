import { useEffect, useState } from 'react'
import api, { TOKEN_STORAGE_KEY } from '../services/api.js'
import authContextValue from './authContextValue.js'

function getErrorMessage(error, fallback) {
  if (!error.response) return 'Unable to connect to the backend. Check the connection and try again.'
  if (error.response.status === 401) return 'Your session has expired. Please sign in again.'
  if (error.response.status === 409) return 'An account with that email already exists.'
  if (error.response.status === 429) return 'Too many attempts. Please wait a moment and try again.'
  const detail = error.response.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map((item) => item.msg).join(' ')
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
      localStorage.setItem(TOKEN_STORAGE_KEY, response.data.access_token)
      await refreshUser()
    } catch (error) {
      clearSession()
      throw new Error(getErrorMessage(error, 'Unable to sign in. Please try again.'), { cause: error })
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

  const logout = () => clearSession()

  useEffect(() => {
    const restoreSession = async () => {
      if (localStorage.getItem(TOKEN_STORAGE_KEY)) {
        try {
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
    <authContextValue.Provider value={{ user, isLoading, login, register, logout, refreshUser }}>
      {children}
    </authContextValue.Provider>
  )
}
