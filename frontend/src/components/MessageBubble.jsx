function MessageBubble({ message, isMine }) {
  return (
    <div className={`flex ${isMine ? 'justify-end' : 'justify-start'} my-1`}>
      <div
        className={`max-w-[85%] sm:max-w-[70%] rounded-2xl px-4 py-3 transition-all ${
          isMine
            ? 'rounded-tr-xs bg-gradient-to-br from-[#0f766e]/95 to-[#0c635c]/95 backdrop-blur-md text-white shadow-[0_4px_18px_rgba(0,30,25,0.25)] border border-teal-300/30'
            : 'rounded-tl-xs bg-white/75 backdrop-blur-md text-txt-primary border border-white/60 shadow-[0_4px_16px_rgba(0,30,25,0.12)]'
        }`}
      >
        <p className="whitespace-pre-wrap break-words [overflow-wrap:anywhere] text-sm leading-relaxed">{message.content}</p>
        <time
          className={`mt-1.5 block text-right font-mono text-[10px] sm:text-[11px] font-medium tracking-tight ${
            isMine ? 'text-teal-100/90' : 'text-txt-timestamp'
          }`}
          dateTime={message.created_at}
        >
          {new Date(message.created_at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}
        </time>
      </div>
    </div>
  )
}

export default MessageBubble
