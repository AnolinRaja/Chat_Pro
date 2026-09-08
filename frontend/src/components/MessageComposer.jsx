import { useState } from 'react'

function MessageComposer({ onSend, disabled }) {
  const [content, setContent] = useState('')

  const submit = async (event) => {
    event.preventDefault()
    const value = content.trim()
    if (!value || disabled) return
    const sent = await onSend(value)
    if (sent) setContent('')
  }

  return (
    <form
      onSubmit={submit}
      className="mx-3 mb-3 sm:mx-6 sm:mb-4 flex items-center gap-2 rounded-full border border-white/50 bg-white/50 backdrop-blur-2xl px-3 py-2 sm:px-4 sm:py-2.5 pb-[max(0.625rem,env(safe-area-inset-bottom,0px))] shadow-[0_16px_45px_-8px_rgba(0,30,25,0.30)] transition-all focus-within:bg-white/75 focus-within:shadow-[0_20px_50px_-8px_rgba(0,30,25,0.40)] focus-within:border-brand/60"
    >
      <label className="sr-only" htmlFor="message-content">Message</label>

      {/* Action / Add button */}
      <button
        type="button"
        disabled={disabled}
        aria-label="Add attachment or action"
        className="flex h-9 w-9 sm:h-10 sm:w-10 shrink-0 items-center justify-center rounded-full border border-white/50 bg-white/40 text-txt-secondary hover:bg-white/80 hover:text-brand transition-all shadow-xs"
      >
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4 sm:h-5 sm:w-5">
          <line x1="12" y1="5" x2="12" y2="19" />
          <line x1="5" y1="12" x2="19" y2="12" />
        </svg>
      </button>

      {/* Input */}
      <input
        id="message-content"
        value={content}
        onChange={(event) => setContent(event.target.value)}
        disabled={disabled}
        maxLength={5000}
        placeholder={disabled ? 'Connecting...' : 'Type a message...'}
        className="min-w-0 flex-1 bg-transparent px-2.5 py-1.5 text-base sm:text-sm text-txt-primary placeholder:text-txt-muted outline-none disabled:opacity-50"
      />

      {/* Emoji button */}
      <button
        type="button"
        disabled={disabled}
        aria-label="Insert emoji"
        className="hidden sm:flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-txt-muted hover:text-txt-primary hover:bg-white/40 transition-all"
      >
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5">
          <circle cx="12" cy="12" r="10" />
          <path d="M8 14s1.5 2 4 2 4-2 4-2" />
          <line x1="9" y1="9" x2="9.01" y2="9" />
          <line x1="15" y1="9" x2="15.01" y2="9" />
        </svg>
      </button>

      {/* Paperclip attachment button */}
      <button
        type="button"
        disabled={disabled}
        aria-label="Attach file"
        className="hidden sm:flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-txt-muted hover:text-txt-primary hover:bg-white/40 transition-all"
      >
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5">
          <path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 18 8.84l-8.59 8.57a2 2 0 0 1-2.83-2.83l8.49-8.48" />
        </svg>
      </button>

      {/* Send button */}
      <button
        type="submit"
        disabled={disabled || !content.trim()}
        aria-label="Send message"
        className="flex h-9 w-9 sm:h-10 sm:w-10 items-center justify-center rounded-full bg-gradient-to-r from-[#0f766e] to-[#0c635c] text-white hover:brightness-110 active:scale-95 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:brightness-100 shadow-md shadow-brand/20 transition-all shrink-0"
      >
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4 sm:h-4.5 sm:w-4.5 -ml-0.5">
          <line x1="22" y1="2" x2="11" y2="13" />
          <polygon points="22 2 15 22 11 13 2 9 22 2" />
        </svg>
      </button>
    </form>
  )
}

export default MessageComposer
