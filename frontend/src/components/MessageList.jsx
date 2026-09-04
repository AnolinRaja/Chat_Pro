import { useEffect, useRef } from 'react'
import MessageBubble from './MessageBubble.jsx'

function MessageList({ messages, currentUserId, isLoading, error }) {
  const containerRef = useRef(null)
  const isNearBottomRef = useRef(true)

  const handleScroll = () => {
    const el = containerRef.current
    if (!el) return
    const distanceToBottom = el.scrollHeight - el.scrollTop - el.clientHeight
    isNearBottomRef.current = distanceToBottom < 120
  }

  useEffect(() => {
    const el = containerRef.current
    if (!el || !messages.length) return
    const lastMessage = messages[messages.length - 1]
    const isMine = lastMessage?.sender_id === currentUserId

    if (isNearBottomRef.current || isMine) {
      el.scrollTop = el.scrollHeight
    }
  }, [messages, currentUserId])

  if (isLoading) return <div className="grid flex-1 place-items-center text-sm text-[#60736e]">Loading messages...</div>
  if (error) return <div role="alert" className="grid flex-1 place-items-center px-6 text-center text-sm text-[#a63d32]">{error}</div>
  if (!messages.length) return <div className="grid flex-1 place-items-center px-6 text-center text-sm text-[#60736e]">No messages yet. Send the first message.</div>

  return (
    <div
      ref={containerRef}
      onScroll={handleScroll}
      className="flex flex-1 flex-col gap-2.5 sm:gap-3 overflow-y-auto px-3 py-4 sm:px-8 sm:py-6"
    >
      {messages.map((message) => <MessageBubble key={message.id} message={message} isMine={message.sender_id === currentUserId} />)}
    </div>
  )
}

export default MessageList
