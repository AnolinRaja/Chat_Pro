import { useEffect, useState } from 'react'
import FormMessage from './FormMessage.jsx'
import { searchUsers } from '../services/conversationService.js'

function getSearchError(error) {
  if (!error.response) return 'The backend is unavailable. Check your connection and try again.'
  if (error.response.status === 401) return 'Your session has expired. Please sign in again.'
  if (error.response.status === 429) return 'Too many searches. Please wait a moment and try again.'
  if (error.response.status === 422) return 'Enter a valid name or email to search.'
  return typeof error.response.data?.detail === 'string' ? error.response.data.detail : 'Unable to search users.'
}

function UserSearch({ currentUserId, onSelect, onClose }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [error, setError] = useState('')
  const [isSearching, setIsSearching] = useState(false)
  const [selectedUserId, setSelectedUserId] = useState('')

  useEffect(() => {
    const trimmedQuery = query.trim()
    if (!trimmedQuery) {
      return undefined
    }

    let active = true
    const timeoutId = setTimeout(async () => {
      setIsSearching(true)
      setError('')
      try {
        const users = await searchUsers(trimmedQuery)
        if (active) setResults(users.filter((user) => user.id !== currentUserId))
      } catch (searchError) {
        if (active) {
          setResults([])
          setError(getSearchError(searchError))
        }
      } finally {
        if (active) setIsSearching(false)
      }
    }, 300)

    return () => {
      active = false
      clearTimeout(timeoutId)
    }
  }, [query, currentUserId])

  const handleQueryChange = (event) => {
    const nextQuery = event.target.value
    setQuery(nextQuery)
    if (!nextQuery.trim()) {
      setResults([])
      setError('')
    }
  }

  useEffect(() => {
    const handleKeyDown = (event) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

  const handleSelect = async (user) => {
    if (selectedUserId) return
    setSelectedUserId(user.id)
    try {
      await onSelect(user)
    } catch {
      setSelectedUserId('')
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-slate-900/40 p-0 sm:p-6 backdrop-blur-md transition-opacity" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
      <div className="flex max-h-[90dvh] w-full max-w-lg flex-col rounded-t-3xl sm:rounded-3xl border border-white/60 bg-white/70 shadow-[0_24px_70px_-15px_rgba(0,30,25,0.35)] backdrop-blur-2xl overflow-hidden" role="dialog" aria-modal="true" aria-labelledby="new-chat-title">
        <div className="flex shrink-0 items-start justify-between gap-3 border-b border-white/30 p-4 sm:p-6 bg-white/30 backdrop-blur-sm">
          <div className="min-w-0">
            <p className="text-[11px] sm:text-xs font-semibold uppercase tracking-[0.16em] text-brand">New chat</p>
            <h2 id="new-chat-title" className="mt-1 text-xl sm:text-2xl font-semibold text-txt-primary">Find someone to message</h2>
          </div>
          <button type="button" onClick={onClose} aria-label="Close new chat" className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-lg text-txt-muted hover:bg-brand-soft hover:text-txt-primary transition-colors">✕</button>
        </div>
        <div className="flex-1 min-h-0 overflow-y-auto p-4 sm:p-6">
          <label className="block text-sm font-medium text-txt-primary" htmlFor="user-search">
            Search people by name or email
            <input
              id="user-search"
              autoFocus
              value={query}
              onChange={handleQueryChange}
              placeholder="Search people..."
              className="mt-2 w-full rounded-xl border border-white/50 bg-white/50 px-3.5 py-2.5 sm:px-4 sm:py-3 text-base sm:text-sm text-txt-primary placeholder:text-txt-muted outline-none focus:bg-white/85 focus:border-brand focus:ring-2 focus:ring-brand/20 shadow-xs"
            />
          </label>
          <div className="mt-4 min-h-32">
            <FormMessage>{error}</FormMessage>
            {!query.trim() && <p className="py-8 text-center text-xs sm:text-sm text-txt-muted">Type a name or email to search.</p>}
            {isSearching && <p className="py-8 text-center text-xs sm:text-sm text-txt-muted">Searching people...</p>}
            {!isSearching && query.trim() && !error && results.length === 0 && <p className="py-8 text-center text-xs sm:text-sm text-txt-muted">No users found.</p>}
            {!isSearching && results.length > 0 && (
              <div className="space-y-2" aria-live="polite">
                {results.map((user) => (
                  <button
                    key={user.id}
                    type="button"
                    disabled={Boolean(selectedUserId)}
                    onClick={() => handleSelect(user)}
                    className={`flex min-h-[52px] w-full items-center gap-3 rounded-xl border p-2.5 sm:p-3 text-left transition ${
                      selectedUserId === user.id ? 'border-brand bg-brand-selected shadow-xs' : 'border-white/40 bg-white/50 hover:border-brand/40 hover:bg-white/80 shadow-xs'
                    }`}
                  >
                    <span className="grid h-10 w-10 sm:h-11 sm:w-11 shrink-0 place-items-center rounded-full bg-txt-primary text-sm font-semibold text-white" aria-hidden="true">
                      {user.name.charAt(0).toUpperCase()}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-semibold text-txt-primary">{user.name}</span>
                      <span className="block truncate text-xs text-txt-muted">{user.email}</span>
                    </span>
                    {selectedUserId === user.id && <span className="ml-auto shrink-0 text-xs font-semibold text-brand">Opening...</span>}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export default UserSearch
