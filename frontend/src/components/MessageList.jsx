import MessageBubble from './MessageBubble.jsx'

function MessageList({ messages, currentUserId, isLoading, error }) {
  if (isLoading) return <div className="grid flex-1 place-items-center text-sm text-[#60736e]">Loading messages...</div>
  if (error) return <div role="alert" className="grid flex-1 place-items-center px-6 text-center text-sm text-[#a63d32]">{error}</div>
  if (!messages.length) return <div className="grid flex-1 place-items-center px-6 text-center text-sm text-[#60736e]">No messages yet. Send the first message.</div>

  return (
    <div className="flex flex-1 flex-col gap-3 overflow-y-auto px-4 py-6 sm:px-8">
      {messages.map((message) => <MessageBubble key={message.id} message={message} isMine={message.sender_id === currentUserId} />)}
    </div>
  )
}

export default MessageList
