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
    <div className="fixed inset-0 z-20 flex items-end justify-center bg-[#172321]/30 p-0 sm:items-center sm:p-6" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
      <div className="w-full max-w-lg rounded-t-2xl bg-white p-5 shadow-2xl sm:rounded-2xl" role="dialog" aria-modal="true" aria-labelledby="new-chat-title">
        <div className="flex items-start justify-between gap-4">
          <div><p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#0f766e]">New chat</p><h2 id="new-chat-title" className="mt-1 text-2xl font-semibold">Find someone to message</h2></div>
          <button type="button" onClick={onClose} aria-label="Close new chat" className="rounded-lg px-3 py-2 text-xl leading-none text-[#60736e] hover:bg-[#edf5f2]">x</button>
        </div>
        <label className="mt-6 block text-sm font-medium" htmlFor="user-search">Search people by name or email<input id="user-search" autoFocus value={query} onChange={handleQueryChange} placeholder="Search people..." className="mt-2 w-full rounded-xl border border-[#cddbd6] px-4 py-3 outline-none focus:border-[#0f766e] focus:ring-2 focus:ring-[#99d6cc]" /></label>
        <div className="mt-5 min-h-32">
          <FormMessage>{error}</FormMessage>
          {!query.trim() && <p className="py-8 text-center text-sm text-[#60736e]">Type a name or email to search.</p>}
          {isSearching && <p className="py-8 text-center text-sm text-[#60736e]">Searching people...</p>}
          {!isSearching && query.trim() && !error && results.length === 0 && <p className="py-8 text-center text-sm text-[#60736e]">No users found.</p>}
          {!isSearching && results.length > 0 && <div className="space-y-2" aria-live="polite">{results.map((user) => <button key={user.id} type="button" disabled={Boolean(selectedUserId)} onClick={() => handleSelect(user)} className={`flex w-full items-center gap-3 rounded-xl border p-3 text-left transition ${selectedUserId === user.id ? 'border-[#0f766e] bg-[#d9f0eb]' : 'border-[#e4ece9] hover:border-[#99d6cc] hover:bg-[#f4f9f7]'}`}><span className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-[#172321] font-semibold text-white" aria-hidden="true">{user.name.charAt(0).toUpperCase()}</span><span className="min-w-0"><span className="block truncate font-semibold text-[#172321]">{user.name}</span><span className="block truncate text-sm text-[#60736e]">{user.email}</span></span>{selectedUserId === user.id && <span className="ml-auto text-xs font-semibold text-[#0f766e]">Opening...</span>}</button>)}</div>}
        </div>
      </div>
    </div>
  )
}

export default UserSearch
