import { useEffect, useState } from 'react'
import ChannelList from '../components/ChannelList.jsx'
import ConversationList from '../components/ConversationList.jsx'
import CreateChannelModal from '../components/CreateChannelModal.jsx'
import JoinOrgModal from '../components/JoinOrgModal.jsx'
import MessageComposer from '../components/MessageComposer.jsx'
import MessageList from '../components/MessageList.jsx'
import OrgRequestsModal from '../components/OrgRequestsModal.jsx'
import UserSearch from '../components/UserSearch.jsx'
import WorkspaceSelector from '../components/WorkspaceSelector.jsx'
import { useAuth } from '../context/useAuth.js'
import { useConversationSocket } from '../hooks/useConversationSocket.js'
import { createConversation, getConversations, getMessages } from '../services/conversationService.js'
import { getMyOrganizations, getOrgConversations } from '../services/organizationService.js'

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

  // Workspace & Organizations
  const [memberships, setMemberships] = useState([])
  const [requests, setRequests] = useState([])
  const [activeWorkspace, setActiveWorkspace] = useState(null) // null = Direct Messages, or membership object
  const [isLoadingOrgs, setIsLoadingOrgs] = useState(true)
  const [isRefreshingOrgs, setIsRefreshingOrgs] = useState(false)
  const [orgError, setOrgError] = useState('')

  // Direct conversations
  const [conversations, setConversations] = useState([])
  const [isLoadingConversations, setIsLoadingConversations] = useState(true)
  const [conversationError, setConversationError] = useState('')

  // Organization channels
  const [channels, setChannels] = useState([])
  const [isLoadingChannels, setIsLoadingChannels] = useState(false)
  const [channelError, setChannelError] = useState('')

  // Active chat state
  const [selectedConversation, setSelectedConversation] = useState(null)
  const [messages, setMessages] = useState([])
  const [messagesConversationId, setMessagesConversationId] = useState(null)
  const [messageError, setMessageError] = useState('')
  const [isLoadingMessages, setIsLoadingMessages] = useState(false)

  // Modals
  const [isNewChatOpen, setIsNewChatOpen] = useState(false)
  const [isJoinOrgOpen, setIsJoinOrgOpen] = useState(false)
  const [isCreateChannelOpen, setIsCreateChannelOpen] = useState(false)
  const [isRequestsModalOpen, setIsRequestsModalOpen] = useState(false)
  const [isCreatingDm, setIsCreatingDm] = useState(false)

  // Reusable organization and requests refresh
  const refreshOrganizations = async (showRefreshIndicator = false) => {
    if (showRefreshIndicator) {
      setIsRefreshingOrgs(true)
    }
    try {
      setOrgError('')
      const result = await getMyOrganizations()
      setMemberships(result.memberships || [])
      setRequests(result.requests || [])
      return result
    } catch (error) {
      const err = formatError(error, 'Unable to load organizations.')
      setOrgError(err)
      throw error
    } finally {
      if (showRefreshIndicator) {
        setIsRefreshingOrgs(false)
      }
      setIsLoadingOrgs(false)
    }
  }

  // Load organizations on mount
  useEffect(() => {
    let active = true
    setIsLoadingOrgs(true)
    getMyOrganizations()
      .then((result) => {
        if (active) {
          setMemberships(result.memberships || [])
          setRequests(result.requests || [])
        }
      })
      .catch((error) => {
        if (active) setOrgError(formatError(error, 'Unable to load organizations.'))
      })
      .finally(() => {
        if (active) setIsLoadingOrgs(false)
      })
    return () => { active = false }
  }, [])

  // Load DM conversations on mount
  useEffect(() => {
    let active = true
    const loadConversations = async () => {
      try {
        setIsLoadingConversations(true)
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

  // Load channels when an organization workspace is active
  useEffect(() => {
    if (!activeWorkspace) {
      setChannels([])
      setChannelError('')
      return undefined
    }

    let active = true
    const loadChannels = async () => {
      setIsLoadingChannels(true)
      setChannelError('')
      try {
        const result = await getOrgConversations(activeWorkspace.organization_id)
        if (active) {
          setChannels(result)
          // Auto-select general or first channel if available
          if (result.length > 0) {
            const general = result.find((c) => c.name === 'general') || result[0]
            setSelectedConversation(general)
          } else {
            setSelectedConversation(null)
          }
        }
      } catch (error) {
        if (active) setChannelError(formatError(error, 'Unable to load channels.'))
      } finally {
        if (active) setIsLoadingChannels(false)
      }
    }

    loadChannels()
    return () => { active = false }
  }, [activeWorkspace])

  // Load message history when selected conversation changes
  useEffect(() => {
    if (!selectedConversation) {
      setMessages([])
      setMessagesConversationId(null)
      return undefined
    }

    let active = true
    setIsLoadingMessages(true)
    setMessageError('')

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
      .finally(() => {
        if (active) setIsLoadingMessages(false)
      })

    return () => { active = false }
  }, [selectedConversation?.id])

  // WebSocket real-time handling
  const handleSocketEvent = (event) => {
    if (event.type === 'message_ack' || event.type === 'message') {
      setMessages((current) => mergeMessage(current, event.data))
    }
    if (event.type === 'error') {
      setMessageError(event.data?.detail || 'The chat server rejected that message.')
    }
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

  // Workspace switching
  const handleSelectWorkspace = (workspace) => {
    if (workspace?.organization_id === activeWorkspace?.organization_id && workspace !== null) {
      return
    }
    setActiveWorkspace(workspace)
    setSelectedConversation(null)
    setMessages([])
    setMessageError('')
  }

  // DM User selection
  const handleUserSelect = async (selectedUser) => {
    if (isCreatingDm) return
    if (selectedUser.id === user?.id) throw new Error('You cannot start a chat with yourself.')
    setIsCreatingDm(true)
    setConversationError('')
    try {
      const existingConversation = conversations.find((conversation) => (
        conversation.participants?.includes(user.id) && conversation.participants?.includes(selectedUser.id)
      ))
      const conversation = existingConversation || await createConversation(selectedUser.id)
      const refreshedConversations = await getConversations()
      setConversations(refreshedConversations)
      const refreshedConversation = refreshedConversations.find((item) => item.id === conversation.id) || conversation
      setSelectedConversation(refreshedConversation)
      setIsNewChatOpen(false)
    } catch (error) {
      setConversationError(error.message || formatError(error, 'Unable to create conversation.'))
      throw error
    } finally {
      setIsCreatingDm(false)
    }
  }

  // Join Org success callback
  const handleJoinOrgSuccess = async (result) => {
    try {
      const orgStatus = await refreshOrganizations()
      const updatedMemberships = orgStatus?.memberships || []

      // If membership was created/active, auto-select it
      const targetOrg = updatedMemberships.find(
        (m) => m.organization_id === result.organization_id || m.org_id === result.org_id
      )
      if (targetOrg) {
        setActiveWorkspace(targetOrg)
      }
    } catch {
      // Ignored, user can retry
    }
  }

  // Open organization requests modal and immediately refresh status
  const handleOpenRequestsModal = () => {
    setIsRequestsModalOpen(true)
    refreshOrganizations(true).catch(() => {})
  }

  // Select an approved organization directly from the requests modal
  const handleSelectWorkspaceFromRequest = (organizationId) => {
    const target = memberships.find((m) => m.organization_id === organizationId)
    if (target) {
      handleSelectWorkspace(target)
    }
  }

  // Channel create success callback
  const handleCreateChannelSuccess = async (newChannel) => {
    if (!activeWorkspace) return
    try {
      const updatedChannels = await getOrgConversations(activeWorkspace.organization_id)
      setChannels(updatedChannels)
      setSelectedConversation(newChannel)
    } catch {
      setChannels((prev) => [...prev, newChannel])
      setSelectedConversation(newChannel)
    }
  }

  const isOrgChannel = Boolean(selectedConversation?.type === 'organization' || selectedConversation?.organization_id)
  const participantLabel = isOrgChannel
    ? `#${selectedConversation.name}`
    : (selectedConversation?.other_user?.name || 'Conversation')

  const descriptionLabel = isOrgChannel
    ? (selectedConversation.description || `${activeWorkspace?.organization_name || 'Organization'} channel`)
    : (socketStatus === 'connected' ? 'Real-time connection active' : socketStatus)

  return (
    <section className="mx-auto flex h-[calc(100vh-73px)] max-w-7xl overflow-hidden bg-white shadow-[0_18px_50px_rgba(25,60,52,0.08)] lg:my-6 lg:h-[calc(100vh-121px)] lg:rounded-2xl lg:border lg:border-[#dbe5e1]">
      {/* Workspace Rail */}
      <WorkspaceSelector
        memberships={memberships}
        requests={requests}
        activeWorkspace={activeWorkspace}
        onSelectWorkspace={handleSelectWorkspace}
        onOpenJoinOrg={() => setIsJoinOrgOpen(true)}
        onOpenRequestsModal={handleOpenRequestsModal}
      />

      {/* Primary Sidebar: Either DMs or Organization Channels */}
      <aside className={`w-full max-w-sm shrink-0 flex-col border-r border-[#dbe5e1] bg-[#fbfcfc] ${selectedConversation ? 'hidden sm:flex' : 'flex'}`}>
        {activeWorkspace === null ? (
          /* Direct Messages Sidebar */
          <>
            <div className="border-b border-[#dbe5e1] px-5 py-5">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#0f766e]">
                Direct Messages
              </p>
              <h1 className="mt-1 truncate text-lg font-semibold text-[#172321]">{user?.name}</h1>
              <p className="truncate text-sm text-[#60736e]">{user?.email}</p>
            </div>
            <div className="flex items-center justify-between px-5 py-4">
              <h2 className="font-semibold text-[#172321]">Conversations</h2>
              <button
                type="button"
                onClick={() => setIsNewChatOpen(true)}
                className="rounded-lg bg-[#0f766e] px-3 py-2 text-xs font-semibold text-white transition hover:bg-[#0b5f59]"
              >
                + New Chat
              </button>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto">
              <ConversationList
                conversations={conversations}
                selectedId={selectedConversation?.id}
                onSelect={setSelectedConversation}
                isLoading={isLoadingConversations}
                error={conversationError}
              />
            </div>
          </>
        ) : (
          /* Organization Channels Sidebar */
          <ChannelList
            organization={activeWorkspace}
            channels={channels}
            selectedId={selectedConversation?.id}
            onSelect={setSelectedConversation}
            isLoading={isLoadingChannels}
            error={channelError}
            onOpenCreateChannel={() => setIsCreateChannelOpen(true)}
            onRetry={() => {
              if (activeWorkspace) {
                setIsLoadingChannels(true)
                getOrgConversations(activeWorkspace.organization_id)
                  .then(setChannels)
                  .catch((err) => setChannelError(formatError(err, 'Unable to load channels.')))
                  .finally(() => setIsLoadingChannels(false))
              }
            }}
          />
        )}
      </aside>

      {/* Chat Window */}
      <main className={`min-w-0 flex-1 flex-col bg-[#eef4f2] ${selectedConversation ? 'flex' : 'hidden sm:flex'}`}>
        {selectedConversation ? (
          <>
            <header className="flex items-center justify-between border-b border-[#dbe5e1] bg-white px-5 py-4 sm:px-8">
              <div className="flex items-center gap-3 min-w-0">
                {/* Back button on mobile */}
                <button
                  type="button"
                  onClick={() => setSelectedConversation(null)}
                  className="sm:hidden rounded-lg p-1.5 text-[#60736e] hover:bg-[#edf5f2]"
                  aria-label="Back to conversations"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" className="h-5 w-5">
                    <polyline points="15 18 9 12 15 6" />
                  </svg>
                </button>
                <div className="min-w-0">
                  <h2 className="font-semibold text-base text-[#172321] truncate">
                    {participantLabel}
                  </h2>
                  <p className="text-xs text-[#60736e] truncate">
                    {descriptionLabel}
                  </p>
                </div>
              </div>
              <div className="shrink-0 flex items-center gap-2">
                <span className="hidden sm:inline-block rounded-full bg-[#edf5f2] px-3 py-1 text-xs font-medium text-[#48615c]">
                  {isOrgChannel ? 'Channel' : 'Direct Message'}
                </span>
              </div>
            </header>

            <MessageList
              messages={messages}
              currentUserId={user?.id}
              isLoading={isLoadingMessages || messagesConversationId !== selectedConversation.id}
              error={messageError}
            />

            <MessageComposer
              onSend={handleSend}
              disabled={socketStatus !== 'connected'}
            />
          </>
        ) : (
          <div className="m-auto px-8 text-center">
            <div className="mx-auto grid h-16 w-16 place-items-center rounded-2xl bg-[#d9f0eb] text-2xl text-[#0f766e]" aria-hidden="true">
              ✦
            </div>
            <h2 className="mt-5 text-2xl font-semibold text-[#172321]">
              {activeWorkspace ? `Welcome to ${activeWorkspace.organization_name}` : 'Choose a conversation'}
            </h2>
            <p className="mt-2 max-w-sm text-sm leading-6 text-[#60736e]">
              {activeWorkspace
                ? 'Select a channel from the sidebar or create a new channel to start messaging.'
                : 'Select a conversation from the sidebar or start one with a teammate.'}
            </p>
          </div>
        )}
      </main>

      {/* Modals */}
      {isNewChatOpen && (
        <UserSearch
          currentUserId={user?.id}
          onSelect={handleUserSelect}
          onClose={() => setIsNewChatOpen(false)}
        />
      )}

      {isJoinOrgOpen && (
        <JoinOrgModal
          isOpen={isJoinOrgOpen}
          onClose={() => setIsJoinOrgOpen(false)}
          onSuccess={handleJoinOrgSuccess}
        />
      )}

      {isCreateChannelOpen && activeWorkspace && (
        <CreateChannelModal
          isOpen={isCreateChannelOpen}
          organization={activeWorkspace}
          onClose={() => setIsCreateChannelOpen(false)}
          onSuccess={handleCreateChannelSuccess}
        />
      )}

      {isRequestsModalOpen && (
        <OrgRequestsModal
          isOpen={isRequestsModalOpen}
          requests={requests}
          memberships={memberships}
          isLoading={isRefreshingOrgs || isLoadingOrgs}
          error={orgError}
          onClose={() => setIsRequestsModalOpen(false)}
          onRefresh={() => refreshOrganizations(true).catch(() => {})}
          onOpenJoinOrg={() => {
            setIsRequestsModalOpen(false)
            setIsJoinOrgOpen(true)
          }}
          onSelectWorkspace={(orgId) => {
            handleSelectWorkspaceFromRequest(orgId)
            setIsRequestsModalOpen(false)
          }}
        />
      )}
    </section>
  )
}

export default ChatPage
