import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { getAccessToken, singleFlightRefresh } from '../services/api.js'
import { useAuth } from './useAuth.js'

const RealtimeContext = createContext(null)

function getWebSocketUserUrl(token) {
  const configuredApiUrl = import.meta.env.VITE_API_BASE_URL || '/api'
  const apiUrl = configuredApiUrl.startsWith('/') ? window.location.origin : configuredApiUrl
  const url = new URL('/ws/user', apiUrl)
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  if (token) url.searchParams.set('token', token)
  return url.toString()
}

export function RealtimeProvider({ children }) {
  const { user } = useAuth()
  const [status, setStatus] = useState('disconnected')

  const socketRef = useRef(null)
  const sessionEpochRef = useRef(0)
  const reconnectTimeoutRef = useRef(null)
  const reconnectAttemptsRef = useRef(0)

  const clearReconnectTimeout = () => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
      reconnectTimeoutRef.current = null
    }
  }

  const disconnectSocket = useCallback((reason = 'Manual disconnect') => {
    sessionEpochRef.current += 1
    clearReconnectTimeout()
    if (socketRef.current) {
      const ws = socketRef.current
      socketRef.current = null
      try {
        ws.close(1000, reason)
      } catch {
        // Ignore socket teardown errors
      }
    }
    setStatus('disconnected')
  }, [])

  const subscribersRef = useRef(new Set())

  const subscribe = useCallback((callback) => {
    subscribersRef.current.add(callback)
    return () => {
      subscribersRef.current.delete(callback)
    }
  }, [])

  const send = useCallback((data) => {
    if (socketRef.current?.readyState !== WebSocket.OPEN) return false
    try {
      const payload = typeof data === 'string' ? data : JSON.stringify(data)
      socketRef.current.send(payload)
      return true
    } catch {
      return false
    }
  }, [])

  useEffect(() => {
    if (!user?.id) {
      disconnectSocket('User logged out')
      return undefined
    }

    const currentEpoch = ++sessionEpochRef.current
    clearReconnectTimeout()

    async function ensureFreshToken() {
      let token = getAccessToken()
      if (!token) {
        try {
          const data = await singleFlightRefresh()
          token = data?.access_token || null
        } catch {
          // Auth refresh failed — AuthContext owns session teardown
        }
      }
      return token
    }

    async function connect() {
      if (sessionEpochRef.current !== currentEpoch) return

      const token = await ensureFreshToken()
      if (sessionEpochRef.current !== currentEpoch) return

      if (!token) {
        setStatus('disconnected')
        return
      }

      setStatus('connecting')
      let ws
      try {
        ws = new WebSocket(getWebSocketUserUrl(token))
      } catch {
        if (sessionEpochRef.current === currentEpoch) {
          setStatus('error')
          scheduleReconnect()
        }
        return
      }

      socketRef.current = ws

      ws.onopen = () => {
        if (sessionEpochRef.current !== currentEpoch || socketRef.current !== ws) {
          try { ws.close(1000, 'Stale socket generation') } catch (_e) { /* ignore */ }
          return
        }
        reconnectAttemptsRef.current = 0
        setStatus('connected')
      }

      ws.onmessage = (event) => {
        if (sessionEpochRef.current !== currentEpoch || socketRef.current !== ws) return
        try {
          const parsed = JSON.parse(event.data)
          subscribersRef.current.forEach((listener) => {
            try { listener(parsed) } catch (_e) { /* ignore */ }
          })
        } catch {
          // Non-JSON socket payload ignored
        }
      }

      ws.onerror = () => {
        if (sessionEpochRef.current !== currentEpoch || socketRef.current !== ws) return
        setStatus('error')
      }

      ws.onclose = (event) => {
        if (socketRef.current === ws) {
          socketRef.current = null
        }
        if (sessionEpochRef.current !== currentEpoch) return

        setStatus('disconnected')
        if (event.code !== 1000) {
          scheduleReconnect()
        }
      }
    }

    function scheduleReconnect() {
      if (sessionEpochRef.current !== currentEpoch) return
      clearReconnectTimeout()
      const attempts = reconnectAttemptsRef.current
      const delay = Math.min(1000 * Math.pow(1.5, attempts), 10000) + Math.random() * 500
      reconnectAttemptsRef.current += 1
      reconnectTimeoutRef.current = setTimeout(() => {
        if (sessionEpochRef.current === currentEpoch) {
          connect()
        }
      }, delay)
    }

    connect()

    const handleOnlineOrVisible = () => {
      if (sessionEpochRef.current !== currentEpoch) return
      if (!socketRef.current || socketRef.current.readyState !== WebSocket.OPEN) {
        clearReconnectTimeout()
        reconnectAttemptsRef.current = 0
        connect()
      }
    }

    window.addEventListener('online', handleOnlineOrVisible)
    const handleVisibility = () => {
      if (document.visibilityState === 'visible') {
        handleOnlineOrVisible()
      }
    }
    document.addEventListener('visibilitychange', handleVisibility)

    return () => {
      window.removeEventListener('online', handleOnlineOrVisible)
      document.removeEventListener('visibilitychange', handleVisibility)
      clearReconnectTimeout()
      if (socketRef.current) {
        const ws = socketRef.current
        socketRef.current = null
        try { ws.close(1000, 'Provider effect unmounting') } catch (_e) { /* ignore */ }
      }
    }
  }, [user?.id, disconnectSocket])

  return (
    <RealtimeContext.Provider value={{ status, subscribe, send }}>
      {children}
    </RealtimeContext.Provider>
  )
}

export function useRealtime() {
  const context = useContext(RealtimeContext)
  if (!context) {
    throw new Error('useRealtime must be used within a RealtimeProvider')
  }
  return context
}
