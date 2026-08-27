import { useEffect, useState } from 'react'
import ConversationList from '../components/ConversationList.jsx'
import MessageComposer from '../components/MessageComposer.jsx'
import MessageList from '../components/MessageList.jsx'
import { useAuth } from '../context/useAuth.js'
import { useConversationSocket } from '../hooks/useConversationSocket.js'
import { createConversation, getConversations, getMessages } from '../services/conversationService.js'

function formatError(error, fallback) {
  if (!error.response) return 'The backend is unavailable. Check that it is running and try again.'
  if (error.response.status === 401) return 'Your session has expired. Please sign in again.'
  if (error.response.status === 403) return 'You do not have access to this conversation.'
  if (error.response.status === 404) return 'That conversation could not be found.'
  if (error.response.status === 422) return 'Please check the conversation details.'
  return typeof error.response.data?.detail === 'string' ? error.response.data.detail : fallback
}

function mergeMessage(messages, message) {
  if (!message?.id || messages.some((item) => item.id === message.id)) return messages
  return [...messages, message].sort((first, second) => new Date(first.created_at) - new Date(second.created_at))
}

function ChatPage() {
  const { user } = useAuth()
  const [conversations, setConversations] = useState([])
  const [selectedConversation, setSelectedConversation] = useState(null)
  const [messages, setMessages] = useState([])
  const [messagesConversationId, setMessagesConversationId] = useState(null)
  const [conversationError, setConversationError] = useState('')
  const [messageError, setMessageError] = useState('')
  const [isLoadingConversations, setIsLoadingConversations] = useState(true)
  const [isLoadingMessages, setIsLoadingMessages] = useState(false)
  const [newUserId, setNewUserId] = useState('')
  const [isCreating, setIsCreating] = useState(false)

  useEffect(() => {
    let active = true
    const loadConversations = async () => {
      try {
        const result = await getConversations()
        if (active) setConversations(result)
      } catch (error) {
        if (active) setConversationError(formatError(error, 'Unable to load conversations.'))
      } finally {
        if (active) setIsLoadingConversations(false)
      }
    }
    loadConversations()
    return () => { active = false }
  }, [])

  useEffect(() => {
    if (!selectedConversation) {
      return undefined
    }
    let active = true
    getMessages(selectedConversation.id)
      .then(({ messages: result }) => {
        if (active) {
          setMessages(result)
          setMessagesConversationId(selectedConversation.id)
        }
      })
      .catch((error) => {
        if (active) {
          setMessageError(formatError(error, 'Unable to load message history.'))
          setMessagesConversationId(selectedConversation.id)
        }
      })
      .finally(() => { if (active) setIsLoadingMessages(false) })
    return () => { active = false }
  }, [selectedConversation])

  const handleSocketEvent = (event) => {
    if (event.type === 'message_ack' || event.type === 'message') setMessages((current) => mergeMessage(current, event.data))
    if (event.type === 'error') setMessageError(event.data?.detail || 'The chat server rejected that message.')
  }

  const { status: socketStatus, send } = useConversationSocket(selectedConversation?.id, {
    onEvent: handleSocketEvent,
    onError: setMessageError,
  })

  const handleSend = async (content) => {
    if (send(content)) {
      setMessageError('')
      return true
    }
    setMessageError('The real-time connection is not ready. Please try again.')
    return false
  }

  const handleCreate = async (event) => {
    event.preventDefault()
    if (!newUserId.trim() || isCreating) return
    setIsCreating(true)
    setConversationError('')
    try {
      const conversation = await createConversation(newUserId.trim())
      setConversations((current) => current.some((item) => item.id === conversation.id) ? current : [conversation, ...current])
      setSelectedConversation(conversation)
      setNewUserId('')
    } catch (error) {
      setConversationError(formatError(error, 'Unable to create conversation.'))
    } finally {
      setIsCreating(false)
    }
  }

  const participant = selectedConversation?.participants.find((id) => id !== user?.id) || selectedConversation?.participants[0]
  const participantLabel = participant ? `User ${participant.slice(-8)}` : 'Conversation'

  return (
    <section className="mx-auto flex h-[calc(100vh-73px)] max-w-7xl overflow-hidden bg-white shadow-[0_18px_50px_rgba(25,60,52,0.08)] lg:my-6 lg:h-[calc(100vh-121px)] lg:rounded-2xl lg:border lg:border-[#dbe5e1]">
      <aside className="flex w-full max-w-sm shrink-0 flex-col border-r border-[#dbe5e1] bg-[#fbfcfc]">
        <div className="border-b border-[#dbe5e1] px-5 py-5">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#0f766e]">Signed in as</p>
          <h1 className="mt-1 truncate text-lg font-semibold">{user?.name}</h1>
          <p className="truncate text-sm text-[#60736e]">{user?.email}</p>
        </div>
        <div className="flex items-center justify-between px-5 py-4"><h2 className="font-semibold">Conversations</h2><span className="text-xs text-[#60736e]">{conversations.length}</span></div>
        <div className="min-h-0 flex-1 overflow-y-auto"><ConversationList conversations={conversations} selectedId={selectedConversation?.id} currentUserId={user?.id} onSelect={setSelectedConversation} isLoading={isLoadingConversations} error={conversationError} /></div>
        <form onSubmit={handleCreate} className="border-t border-[#dbe5e1] p-4">
          <label className="text-xs font-semibold uppercase tracking-[0.12em] text-[#60736e]" htmlFor="other-user-id">Start with user ID</label>
          <div className="mt-2 flex gap-2"><input id="other-user-id" value={newUserId} onChange={(event) => setNewUserId(event.target.value)} placeholder="MongoDB user ID" className="min-w-0 flex-1 rounded-lg border border-[#cddbd6] px-3 py-2 text-xs outline-none focus:border-[#0f766e]" /><button type="submit" disabled={isCreating || !newUserId.trim()} className="rounded-lg bg-[#172321] px-3 py-2 text-xs font-semibold text-white disabled:opacity-50">{isCreating ? '...' : 'Start'}</button></div>
        </form>
      </aside>
      <main className="hidden min-w-0 flex-1 flex-col bg-[#eef4f2] sm:flex">
        {selectedConversation ? <>
          <header className="flex items-center justify-between border-b border-[#dbe5e1] bg-white px-5 py-4 sm:px-8"><div><h2 className="font-semibold">{participantLabel}</h2><p className="text-xs text-[#60736e]">{socketStatus === 'connected' ? 'Real-time connection active' : socketStatus}</p></div><span className="text-xs text-[#60736e]">{selectedConversation.participants.length} participants</span></header>
          <MessageList messages={messages} currentUserId={user?.id} isLoading={isLoadingMessages || messagesConversationId !== selectedConversation.id} error={messageError} />
          <MessageComposer onSend={handleSend} disabled={socketStatus !== 'connected'} />
        </> : <div className="m-auto px-8 text-center"><div className="mx-auto grid h-16 w-16 place-items-center rounded-2xl bg-[#d9f0eb] text-2xl text-[#0f766e]" aria-hidden="true">✦</div><h2 className="mt-5 text-2xl font-semibold">Choose a conversation</h2><p className="mt-2 max-w-sm text-sm leading-6 text-[#60736e]">Select a conversation from the sidebar or start one with a user ID.</p></div>}
      </main>
    </section>
  )
}

export default ChatPage
