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
    <form onSubmit={submit} className="flex gap-2 border-t border-[#dbe5e1] bg-white p-3 sm:p-4">
      <label className="sr-only" htmlFor="message-content">Message</label>
      <input id="message-content" value={content} onChange={(event) => setContent(event.target.value)} disabled={disabled} maxLength={5000} placeholder={disabled ? 'Connecting...' : 'Write a message...'} className="min-w-0 flex-1 rounded-xl border border-[#cddbd6] px-4 py-3 text-sm outline-none focus:border-[#0f766e] focus:ring-2 focus:ring-[#99d6cc] disabled:bg-[#f4f7f6]" />
      <button type="submit" disabled={disabled || !content.trim()} className="rounded-xl bg-[#0f766e] px-4 py-3 text-sm font-semibold text-white hover:bg-[#0b5f59] disabled:cursor-not-allowed disabled:opacity-50">Send</button>
    </form>
  )
}

export default MessageComposer
