import { useEffect, useRef } from 'react'
import { useRealtime } from '../context/RealtimeContext.jsx'

export function useConversationSocket(conversationId, { onEvent, onError } = {}) {
  const { status, subscribe } = useRealtime()
  const onEventRef = useRef(onEvent)
  const onErrorRef = useRef(onError)

  useEffect(() => {
    onEventRef.current = onEvent
    onErrorRef.current = onError
  }, [onEvent, onError])

  useEffect(() => {
    const unsubscribe = subscribe((event) => {
      try {
        onEventRef.current?.(event)
      } catch {
        onErrorRef.current?.('Received an invalid message from the chat server.')
      }
    })
    return () => {
      unsubscribe()
    }
  }, [subscribe])

  return { status }
}

