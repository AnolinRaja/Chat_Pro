import { useContext } from 'react'
import authContextValue from './authContextValue.js'

export function useAuth() {
  const context = useContext(authContextValue)
  if (!context) throw new Error('useAuth must be used within AuthProvider')
  return context
}
