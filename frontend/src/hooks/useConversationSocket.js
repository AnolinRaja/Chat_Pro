import { useCallback, useEffect, useRef, useState } from 'react'
import { getAccessToken } from '../services/api.js'

function getWebSocketUrl(conversationId) {
  const configuredApiUrl = import.meta.env.VITE_API_BASE_URL || '/api'
  const apiUrl = configuredApiUrl.startsWith('/') ? window.location.origin : configuredApiUrl
  const url = new URL(`/ws/conversations/${conversationId}`, apiUrl)
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  const token = getAccessToken()
  if (token) url.searchParams.set('token', token)
  return url.toString()
}

export function useConversationSocket(conversationId, { onEvent, onError }) {
  const socketRef = useRef(null)
  const onEventRef = useRef(onEvent)
  const onErrorRef = useRef(onError)
  const reconnectTimeoutRef = useRef(null)
  const reconnectAttemptsRef = useRef(0)
  const [status, setStatus] = useState('disconnected')

  useEffect(() => {
    onEventRef.current = onEvent
    onErrorRef.current = onError
  }, [onEvent, onError])

  useEffect(() => {
    if (!conversationId) {
      return undefined
    }

    let isCancelled = false

    function connect() {
      if (isCancelled) return

      const token = getAccessToken()
      if (!token) {
        // If no token yet (e.g. during initial restore), try reconnecting shortly
        setStatus('connecting')
        reconnectTimeoutRef.current = setTimeout(() => {
          if (!isCancelled) connect()
        }, 1000)
        return
      }

      setStatus('connecting')
      let socket
      try {
        socket = new WebSocket(getWebSocketUrl(conversationId))
      } catch {
        setStatus('error')
        scheduleReconnect()
        return
      }

      socketRef.current = socket

      socket.onopen = () => {
        if (isCancelled || socketRef.current !== socket) {
          socket.close()
          return
        }
        reconnectAttemptsRef.current = 0
        setStatus('connected')
      }

      socket.onmessage = (event) => {
        if (isCancelled || socketRef.current !== socket) return
        try {
          const parsed = JSON.parse(event.data)
          onEventRef.current?.(parsed)
        } catch {
          onErrorRef.current?.('Received an invalid message from the chat server.')
        }
      }

      socket.onerror = () => {
        if (isCancelled || socketRef.current !== socket) return
        setStatus('error')
      }

      socket.onclose = (event) => {
        if (socketRef.current === socket) {
          socketRef.current = null
        }
        if (isCancelled) return

        setStatus('disconnected')
        // Code 1000 means normal closure; 1008 is auth/policy violation
        if (event.code !== 1000 && event.code !== 1008) {
          scheduleReconnect()
        }
      }
    }

    function scheduleReconnect() {
      if (isCancelled) return
      clearTimeout(reconnectTimeoutRef.current)
      const delay = Math.min(1000 * Math.pow(1.5, reconnectAttemptsRef.current), 10000)
      reconnectAttemptsRef.current += 1
      reconnectTimeoutRef.current = setTimeout(() => {
        if (!isCancelled) {
          connect()
        }
      }, delay)
    }

    connect()

    return () => {
      isCancelled = true
      clearTimeout(reconnectTimeoutRef.current)
      if (socketRef.current) {
        const activeSocket = socketRef.current
        socketRef.current = null
        try {
          activeSocket.close(1000, 'Conversation changed or unmounted')
        } catch {
          // Ignore close errors on teardown
        }
      }
    }
  }, [conversationId])

  const send = useCallback((content) => {
    if (socketRef.current?.readyState !== WebSocket.OPEN) return false
    try {
      socketRef.current.send(JSON.stringify({ content }))
      return true
    } catch {
      return false
    }
  }, [])

  return { status: conversationId ? status : 'disconnected', send }
}
