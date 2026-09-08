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
      className="flex items-center gap-2 border-t border-line-glass bg-glass-composer backdrop-blur-xl p-2.5 sm:p-4 pb-[max(0.625rem,env(safe-area-inset-bottom,0px))] sm:pb-4 shadow-composer"
    >
      <label className="sr-only" htmlFor="message-content">Message</label>
      <input
        id="message-content"
        value={content}
        onChange={(event) => setContent(event.target.value)}
        disabled={disabled}
        maxLength={5000}
        placeholder={disabled ? 'Connecting...' : 'Write a message...'}
        className="min-w-0 flex-1 rounded-xl border border-line-glass bg-glass-card px-3.5 py-2.5 sm:px-4 sm:py-3 text-base sm:text-sm text-txt-primary placeholder:text-txt-muted outline-none focus:border-brand focus:ring-2 focus:ring-brand-soft disabled:bg-line-subtle transition-all"
      />
      <button
        type="submit"
        disabled={disabled || !content.trim()}
        className="flex min-h-[44px] min-w-[44px] items-center justify-center rounded-xl bg-brand px-4 py-2.5 sm:px-5 sm:py-3 text-sm font-semibold text-white hover:bg-brand-hover active:bg-brand-active disabled:cursor-not-allowed disabled:opacity-50 shadow-xs transition-colors"
      >
        <span>Send</span>
      </button>
    </form>
  )
}

export default MessageComposer
