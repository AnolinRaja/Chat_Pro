import { useEffect, useRef, useState } from 'react'
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
  const [status, setStatus] = useState('disconnected')

  useEffect(() => {
    onEventRef.current = onEvent
    onErrorRef.current = onError
  }, [onEvent, onError])

  useEffect(() => {
    if (!conversationId) {
      return undefined
    }

    const socket = new WebSocket(getWebSocketUrl(conversationId))
    socketRef.current = socket

    socket.onopen = () => setStatus('connected')
    socket.onmessage = (event) => {
      try {
        onEventRef.current(JSON.parse(event.data))
      } catch {
        onErrorRef.current('Received an invalid message from the chat server.')
      }
    }
    socket.onerror = () => {
      setStatus('error')
      onErrorRef.current('The real-time connection could not be established.')
    }
    socket.onclose = () => {
      setStatus('disconnected')
      if (socketRef.current === socket) socketRef.current = null
    }

    return () => {
      socket.close()
      if (socketRef.current === socket) socketRef.current = null
    }
  }, [conversationId])

  const send = (content) => {
    if (socketRef.current?.readyState !== WebSocket.OPEN) return false
    socketRef.current.send(JSON.stringify({ content }))
    return true
  }

  return { status: conversationId && status === 'disconnected' ? 'connecting' : status, send }
}
