function MessageBubble({ message, isMine }) {
  return (
    <div className={`flex ${isMine ? 'justify-end' : 'justify-start'}`}>
      <div className={`max-w-[85%] rounded-2xl px-3.5 py-2.5 sm:max-w-[65%] sm:px-4 sm:py-3 ${isMine ? 'rounded-br-sm bg-[#0f766e] text-white' : 'rounded-bl-sm bg-white text-[#172321] shadow-xs border border-[#e2ece9]'}`}>
        <p className="whitespace-pre-wrap break-words [overflow-wrap:anywhere] text-sm leading-6">{message.content}</p>
        <time className={`mt-1 block text-right text-[10px] sm:text-[11px] ${isMine ? 'text-[#c4e8e1]' : 'text-[#78908a]'}`} dateTime={message.created_at}>{new Date(message.created_at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}</time>
      </div>
    </div>
  )
}

export default MessageBubble
