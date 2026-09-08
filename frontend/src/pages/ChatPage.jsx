import { useEffect, useRef, useState } from 'react'
import ChannelList from '../components/ChannelList.jsx'
import ConversationList from '../components/ConversationList.jsx'
import CreateChannelModal from '../components/CreateChannelModal.jsx'
import JoinOrgModal from '../components/JoinOrgModal.jsx'
import MessageComposer from '../components/MessageComposer.jsx'
import MessageList from '../components/MessageList.jsx'
import OrgRequestsModal from '../components/OrgRequestsModal.jsx'
import UserSearch from '../components/UserSearch.jsx'
import WorkspaceSelector from '../components/WorkspaceSelector.jsx'
import { ChatProSymbol } from '../components/ChatProLogo.jsx'
import { useAuth } from '../context/useAuth.js'
import { useConversationSocket } from '../hooks/useConversationSocket.js'
import { createConversation, getConversations, getMessages, markConversationRead, sendMessage } from '../services/conversationService.js'
import { getMyOrganizations, getOrgConversations } from '../services/organizationService.js'
import { getSavedChatContext, saveChatContext } from '../utils/chatSessionStorage.js'
import {
  applyReadState,
  clearConversationUnread,
  compareCanonicalMessages,
  hydrateActivityState,
  recordMessageActivity,
  sortByNewestActivity,
} from '../utils/activityUtils.js'

function formatError(error, fallback) {
  if (!error.response) return 'The backend is unavailable. Check that it is running and try again.'
  if (error.response.status === 401) return 'Your session has expired. Please sign in again.'
  if (error.response.status === 403) return 'You do not have access to this conversation.'
  if (error.response.status === 404) return 'That conversation could not be found.'
  if (error.response.status === 422) return 'Please check the conversation details.'
  return typeof error.response.data?.detail === 'string' ? error.response.data.detail : fallback
}

function mergeMessage(messages, message) {
  if (!message?.id || messages.some((item) => String(item.id) === String(message.id))) return messages
  return [...messages, message].sort(compareCanonicalMessages)
}


function ChatPage() {
  const { user } = useAuth()
  const savedContextRef = useRef(getSavedChatContext(user?.id))

  // Search filter
  const [searchQuery, setSearchQuery] = useState('')

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
  const selectedConversationRef = useRef(selectedConversation)
  useEffect(() => {
    selectedConversationRef.current = selectedConversation
  }, [selectedConversation])

  const [messages, setMessages] = useState([])
  const messagesRef = useRef(messages)
  useEffect(() => {
    messagesRef.current = messages
  }, [messages])

  const [messagesConversationId, setMessagesConversationId] = useState(null)
  const [messageError, setMessageError] = useState('')
  const [isLoadingMessages, setIsLoadingMessages] = useState(false)

  // In-memory activity map: { [conversationId]: { latestPreview, latestMessageAt, unreadCount } }
  const [activityState, setActivityState] = useState({})
  const activityStateRef = useRef(activityState)
  useEffect(() => {
    activityStateRef.current = activityState
  }, [activityState])

  const pendingReadCursorRef = useRef({})
  const lastAckedReadMsgIdRef = useRef({})
  const isReadRequestInFlightRef = useRef({})
  const debouncedReadTimersRef = useRef({})

  const processPendingRead = async (convId) => {
    if (!convId) return
    if (isReadRequestInFlightRef.current[convId]) return

    // Safety guard: ensure user is still viewing this exact conversation
    if (selectedConversationRef.current && String(selectedConversationRef.current.id) !== String(convId)) {
      return
    }

    const pending = pendingReadCursorRef.current[convId]
    if (!pending || !pending.msgId) return

    // If backend has already acknowledged this message ID, skip
    if (lastAckedReadMsgIdRef.current[convId] === pending.msgId) {
      pendingReadCursorRef.current[convId] = null
      return
    }

    const { msgId, msgCreatedAt } = pending

    try {
      isReadRequestInFlightRef.current[convId] = true

      // Apply read state locally
      setActivityState((prev) =>
        applyReadState(prev, convId, {
          lastReadMessageId: msgId,
          lastReadMessageCreatedAt: msgCreatedAt,
        })
      )

      // Send POST /conversations/{id}/read
      await markConversationRead(convId, msgId)

      // Successfully acknowledged by backend!
      lastAckedReadMsgIdRef.current[convId] = msgId

      // Clear pending if it hasn't changed while request was in flight
      if (pendingReadCursorRef.current[convId]?.msgId === msgId) {
        pendingReadCursorRef.current[convId] = null
      }
    } catch (err) {
      // Transient failure: Do NOT set lastAckedReadMsgIdRef. Keep pendingReadCursorRef intact for retries.
      void err

      // Schedule explicit retry after 2 seconds if user is still on this conversation
      if (debouncedReadTimersRef.current[convId]) {
        clearTimeout(debouncedReadTimersRef.current[convId])
      }
      debouncedReadTimersRef.current[convId] = setTimeout(() => {
        if (selectedConversationRef.current && String(selectedConversationRef.current.id) === String(convId)) {
          processPendingRead(convId).catch((e) => { void e })
        }
      }, 2000)
    } finally {
      isReadRequestInFlightRef.current[convId] = false

      // If a newer pending message arrived while request was in flight, process it now
      const nextPending = pendingReadCursorRef.current[convId]
      if (nextPending && nextPending.msgId !== lastAckedReadMsgIdRef.current[convId]) {
        processPendingRead(convId).catch((err) => { void err })
      }
    }
  }

  const queueActiveMessageRead = (convId, msgId, msgCreatedAt) => {
    if (!convId || !msgId) return

    // Record newest pending cursor (coalesces rapid messages: M101 replaced by M102)
    pendingReadCursorRef.current[convId] = { msgId, msgCreatedAt }

    if (debouncedReadTimersRef.current[convId]) {
      clearTimeout(debouncedReadTimersRef.current[convId])
    }

    debouncedReadTimersRef.current[convId] = setTimeout(() => {
      // Safety guard: Ensure user is still viewing this exact conversation
      if (selectedConversationRef.current && String(selectedConversationRef.current.id) === String(convId)) {
        processPendingRead(convId)
      }
    }, 150)
  }

  const [activeUserId, setActiveUserId] = useState(user?.id)

  // Reset in-memory activity state when user changes (User isolation)
  if (activeUserId !== user?.id) {
    setActiveUserId(user?.id)
    setActivityState({})
  }

  // Clear pending read refs and timers on user/session change
  useEffect(() => {
    pendingReadCursorRef.current = {}
    lastAckedReadMsgIdRef.current = {}
    isReadRequestInFlightRef.current = {}
    Object.values(debouncedReadTimersRef.current).forEach((timer) => clearTimeout(timer))
    debouncedReadTimersRef.current = {}
  }, [user?.id])

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
    getMyOrganizations()
      .then((result) => {
        if (active) {
          const fetchedMemberships = result.memberships || []
          setMemberships(fetchedMemberships)
          setRequests(result.requests || [])

          // Restore saved organization if valid
          const targetOrgId = savedContextRef.current.organizationId
          if (targetOrgId) {
            const matchingOrg = fetchedMemberships.find(
              (m) => String(m.organization_id) === String(targetOrgId) || String(m.org_id) === String(targetOrgId)
            )
            if (matchingOrg) {
              setActiveWorkspace(matchingOrg)
            } else {
              // Stale organization is no longer accessible
              savedContextRef.current.organizationId = null
              savedContextRef.current.conversationId = null
              if (user?.id) {
                saveChatContext(user.id, { organizationId: null, conversationId: null })
              }
            }
          }
        }
      })
      .catch((error) => {
        if (active) setOrgError(formatError(error, 'Unable to load organizations.'))
      })
      .finally(() => {
        if (active) setIsLoadingOrgs(false)
      })
    return () => { active = false }
  }, [user?.id])

  // Load DM conversations on mount
  useEffect(() => {
    let active = true
    const loadConversations = async () => {
      try {
        setIsLoadingConversations(true)
        const restInitiatedAt = new Date().toISOString()
        const result = await getConversations()
        if (active) {
          setActivityState((prev) => {
            const hydrated = hydrateActivityState(prev, result, restInitiatedAt)
            const sorted = sortByNewestActivity(result, hydrated)
            setConversations(sorted)
            return hydrated
          })
          // If on Direct Messages workspace, restore saved DM conversation if valid
          if (!savedContextRef.current.organizationId && savedContextRef.current.conversationId) {
            const matchingConv = result.find((c) => String(c.id) === String(savedContextRef.current.conversationId))
            if (matchingConv) {
              setSelectedConversation(matchingConv)
              savedContextRef.current.conversationId = null
            } else {
              // Stale DM conversation
              savedContextRef.current.conversationId = null
              if (user?.id) {
                saveChatContext(user.id, { organizationId: null, conversationId: null })
              }
            }
          }
        }
      } catch (error) {
        if (active) setConversationError(formatError(error, 'Unable to load conversations.'))
      } finally {
        if (active) setIsLoadingConversations(false)
      }
    }
    loadConversations()
    return () => { active = false }
  }, [user?.id])

  // Load channels when an organization workspace is active
  useEffect(() => {
    if (!activeWorkspace) {
      queueMicrotask(() => {
        setChannels([])
        setChannelError('')
      })
      return undefined
    }

    let active = true
    const loadChannels = async () => {
      setIsLoadingChannels(true)
      setChannelError('')
      try {
        const restInitiatedAt = new Date().toISOString()
        const result = await getOrgConversations(activeWorkspace.organization_id)
        if (active) {
          setActivityState((prev) => {
            const hydrated = hydrateActivityState(prev, result, restInitiatedAt)
            const sorted = sortByNewestActivity(result, hydrated)
            setChannels(sorted)
            return hydrated
          })
          // Restore saved channel if matching this organization
          const targetConvId = savedContextRef.current.conversationId
          const matchingChannel = targetConvId ? result.find((c) => String(c.id) === String(targetConvId)) : null

          if (matchingChannel) {
            setSelectedConversation(matchingChannel)
            savedContextRef.current.conversationId = null
          } else if (result.length > 0) {
            // Auto-select general or first channel if available
            const general = result.find((c) => c.name === 'general') || result[0]
            setSelectedConversation(general)
            if (user?.id) {
              saveChatContext(user.id, {
                organizationId: activeWorkspace.organization_id,
                conversationId: general?.id || null,
              })
            }
            savedContextRef.current.conversationId = null
          } else {
            setSelectedConversation(null)
            if (user?.id) {
              saveChatContext(user.id, {
                organizationId: activeWorkspace.organization_id,
                conversationId: null,
              })
            }
            savedContextRef.current.conversationId = null
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
  }, [activeWorkspace, user?.id])

  // Load message history when selected conversation changes
  useEffect(() => {
    if (!selectedConversation) {
      queueMicrotask(() => {
        setMessages([])
        setMessagesConversationId(null)
      })
      return
    }

    let active = true
    const loadMessageHistory = async () => {
      setIsLoadingMessages(true)
      setMessageError('')
      try {
        const { messages: result } = await getMessages(selectedConversation.id)
        if (active) {
          const sortedMessages = [...(result || [])].sort(compareCanonicalMessages)
          setMessages(sortedMessages)
          setMessagesConversationId(selectedConversation.id)

          if (sortedMessages.length > 0) {
            const newestMsg = sortedMessages[sortedMessages.length - 1]
            // Mark read locally and send POST /read via queueActiveMessageRead
            queueActiveMessageRead(selectedConversation.id, newestMsg.id, newestMsg.created_at)
          } else {
            // Empty conversation: unreadCount = 0, no POST /read called
            setActivityState((prev) =>
              applyReadState(prev, selectedConversation.id, {
                lastReadMessageId: null,
                lastReadMessageCreatedAt: null,
              })
            )
          }
        }
      } catch (error) {
        if (active) {
          setMessageError(formatError(error, 'Unable to load message history.'))
          setMessagesConversationId(selectedConversation.id)
        }
      } finally {
        if (active) setIsLoadingMessages(false)
      }
    }

    loadMessageHistory()
    return () => { active = false }
  }, [selectedConversation?.id])

  // WebSocket real-time handling
  const handleSocketEvent = (event) => {
    if (!event) return

    const eventConvId = event.conversation_id || event.message?.conversation_id || event.data?.conversation_id
    if (!eventConvId) return

    if (event.type === 'conversation.read') {
      const { user_id, last_read_message_id, last_read_message_created_at } = event
      if (last_read_message_id) {
        let resolvedCreatedAt = last_read_message_created_at || null
        if (!resolvedCreatedAt) {
          if (selectedConversationRef.current && String(selectedConversationRef.current.id) === String(eventConvId)) {
            const matchingMsg = messagesRef.current.find((m) => String(m.id) === String(last_read_message_id))
            if (matchingMsg) resolvedCreatedAt = matchingMsg.created_at
          }
          if (!resolvedCreatedAt) {
            const existingAct = activityStateRef.current[eventConvId]
            if (existingAct && String(existingAct.latestMessageId) === String(last_read_message_id)) {
              resolvedCreatedAt = existingAct.latestMessageAt
            }
          }
        }
        // NOTE: If resolvedCreatedAt is null, pass null. Do NOT fallback to last_read_at or wall-clock time!

        setActivityState((prev) =>
          applyReadState(prev, eventConvId, {
            lastReadMessageId: last_read_message_id,
            lastReadMessageCreatedAt: resolvedCreatedAt,
            currentUserId: user?.id,
            eventUserId: user_id,
          })
        )
      }
    } else if (event.type === 'message.created' || event.type === 'message' || event.type === 'message_ack') {
      const msg = event.message || event.data
      if (msg) {
        const isCurrentConv = selectedConversationRef.current && String(eventConvId) === String(selectedConversationRef.current.id)
        if (isCurrentConv) {
          setMessages((current) => mergeMessage(current, msg))
        }

        const msgTimestamp = msg.created_at || new Date().toISOString()

        // Update in-memory activity state
        setActivityState((prev) =>
          recordMessageActivity(prev, eventConvId, {
            content: msg.content,
            timestamp: msgTimestamp,
            messageId: msg.id,
            senderId: msg.sender_id,
            currentUserId: user?.id,
            isCurrentlySelected: Boolean(isCurrentConv),
          })
        )

        // ISSUE 2 FIX: If realtime message arrived for currently active chat, queue debounced POST /read
        if (isCurrentConv) {
          queueActiveMessageRead(eventConvId, msg.id, msgTimestamp)
        }

        // Reorder conversations or channels strictly based on newest activity timestamp
        setConversations((prev) => {
          if (prev.some((c) => String(c.id) === String(eventConvId))) {
            const updated = prev.map((c) => (String(c.id) === String(eventConvId) ? { ...c, updated_at: msgTimestamp } : c))
            return sortByNewestActivity(updated, activityStateRef.current)
          }
          // If conversation isn't in current list, fetch updated conversations from backend
          getConversations()
            .then((result) => setConversations(sortByNewestActivity(result, activityStateRef.current)))
            .catch(() => {})
          return prev
        })

        setChannels((prev) => {
          if (prev.some((c) => String(c.id) === String(eventConvId))) {
            const updated = prev.map((c) => (String(c.id) === String(eventConvId) ? { ...c, updated_at: msgTimestamp } : c))
            return sortByNewestActivity(updated, activityStateRef.current)
          }
          if (activeWorkspace) {
            getOrgConversations(activeWorkspace.organization_id)
              .then((result) => setChannels(sortByNewestActivity(result, activityStateRef.current)))
              .catch(() => {})
          }
          return prev
        })
      }
    } else if (event.type === 'error') {
      setMessageError(event.data?.detail || event.detail || 'The chat server rejected that message.')
    }
  }


  const { status: socketStatus } = useConversationSocket(selectedConversation?.id, {
    onEvent: handleSocketEvent,
    onError: setMessageError,
  })

  const handleSend = async (content) => {
    if (!selectedConversation) return false

    const nowIso = new Date().toISOString()

    try {
      setMessageError('')
      const savedMessage = await sendMessage(selectedConversation.id, content)
      setMessages((current) => mergeMessage(current, savedMessage))
      const savedTimestamp = savedMessage.created_at || nowIso
      setActivityState((prev) =>
        recordMessageActivity(prev, selectedConversation.id, {
          content: savedMessage.content || content,
          timestamp: savedTimestamp,
          messageId: savedMessage.id,
          senderId: user?.id,
          currentUserId: user?.id,
          isCurrentlySelected: true,
        })
      )
      setConversations((prev) => {
        if (prev.some((c) => String(c.id) === String(selectedConversation.id))) {
          const updated = prev.map((c) => (String(c.id) === String(selectedConversation.id) ? { ...c, updated_at: savedTimestamp } : c))
          return sortByNewestActivity(updated, activityStateRef.current)
        }
        return prev
      })
      setChannels((prev) => {
        if (prev.some((c) => String(c.id) === String(selectedConversation.id))) {
          const updated = prev.map((c) => (String(c.id) === String(selectedConversation.id) ? { ...c, updated_at: savedTimestamp } : c))
          return sortByNewestActivity(updated, activityStateRef.current)
        }
        return prev
      })
      return true
    } catch (error) {
      setMessageError(formatError(error, 'Unable to send message.'))
      return false
    }
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
    if (user?.id) {
      saveChatContext(user.id, {
        organizationId: workspace?.organization_id || null,
        conversationId: null,
      })
    }
  }

  // Conversation selection (selection clears unread count but does NOT artificially change activity timestamp)
  const handleSelectConversation = (conversation) => {
    setSelectedConversation(conversation)
    if (conversation?.id) {
      setActivityState((prev) => clearConversationUnread(prev, conversation.id))
    }
    if (user?.id) {
      saveChatContext(user.id, {
        organizationId: activeWorkspace?.organization_id || null,
        conversationId: conversation?.id || null,
      })
    }
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
      const sorted = sortByNewestActivity(refreshedConversations, activityStateRef.current)
      setConversations(sorted)
      const refreshedConversation = sorted.find((item) => item.id === conversation.id) || conversation
      setSelectedConversation(refreshedConversation)
      if (user?.id) {
        saveChatContext(user.id, {
          organizationId: null,
          conversationId: refreshedConversation?.id || null,
        })
      }
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
        handleSelectWorkspace(targetOrg)
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
      const sorted = sortByNewestActivity(updatedChannels, activityStateRef.current)
      setChannels(sorted)
      setSelectedConversation(newChannel)
      if (user?.id) {
        saveChatContext(user.id, {
          organizationId: activeWorkspace.organization_id,
          conversationId: newChannel?.id || null,
        })
      }
    } catch {
      setChannels((prev) => sortByNewestActivity([...prev, newChannel], activityStateRef.current))
      setSelectedConversation(newChannel)
      if (user?.id) {
        saveChatContext(user.id, {
          organizationId: activeWorkspace.organization_id,
          conversationId: newChannel?.id || null,
        })
      }
    }
  }

  const isOrgChannel = Boolean(selectedConversation?.type === 'organization' || selectedConversation?.organization_id)
  const participantLabel = isOrgChannel
    ? `#${selectedConversation.name}`
    : (selectedConversation?.other_user?.name || 'Conversation')

  const descriptionLabel = isOrgChannel
    ? (selectedConversation.description || `${activeWorkspace?.organization_name || 'Organization'} channel`)
    : (socketStatus === 'connected' ? 'Real-time connection active' : socketStatus)

  const filteredConversations = conversations.filter((c) => {
    if (!searchQuery.trim()) return true
    const query = searchQuery.toLowerCase()
    const name = c.other_user?.name?.toLowerCase() || ''
    const email = c.other_user?.email?.toLowerCase() || ''
    const preview = (activityState[c.id]?.latestPreview || '').toLowerCase()
    return name.includes(query) || email.includes(query) || preview.includes(query)
  })

  return (
    <section className="mx-auto flex h-[calc(100dvh-57px)] sm:h-[calc(100vh-73px)] w-full max-w-7xl overflow-hidden bg-white/10 backdrop-blur-xl shadow-[0_24px_70px_-15px_rgba(0,30,25,0.35)] lg:my-6 lg:h-[calc(100vh-121px)] lg:rounded-3xl lg:border lg:border-white/30 transition-all">
      {/* Workspace Rail */}
      <WorkspaceSelector
        memberships={memberships}
        requests={requests}
        activeWorkspace={activeWorkspace}
        onSelectWorkspace={handleSelectWorkspace}
        onOpenJoinOrg={() => setIsJoinOrgOpen(true)}
        onOpenRequestsModal={handleOpenRequestsModal}
        user={user}
        className={selectedConversation ? 'hidden sm:flex' : 'flex'}
      />

      {/* Primary Sidebar: Either DMs or Organization Channels */}
      <aside className={`w-full sm:max-w-sm shrink-0 flex-col border-r border-white/30 bg-white/30 backdrop-blur-xl ${selectedConversation ? 'hidden sm:flex' : 'flex flex-1 sm:flex-initial'}`}>
        {activeWorkspace === null ? (
          /* Direct Messages Sidebar */
          <>
            <div className="border-b border-white/30 px-3.5 sm:px-5 py-3 sm:py-3.5 bg-white/20 backdrop-blur-sm">
              {/* Sidebar Brand Identity */}
              <div className="flex items-center gap-2.5 mb-3">
                <div className="grid h-9 w-9 place-items-center rounded-xl bg-white/50 p-1 backdrop-blur-md border border-white/60 shadow-xs">
                  <ChatProSymbol size={22} glow />
                </div>
                <div className="min-w-0 flex-1">
                  <h1 className="text-sm sm:text-base font-bold text-txt-primary truncate leading-tight font-display">
                    {user?.name ? `${user.name}'s ` : ''}<span className="text-teal-700">chat</span><span className="text-brand font-black">PRO</span>
                  </h1>
                </div>
              </div>

              {/* Search Pill + Compose Button Row */}
              <div className="flex items-center gap-2">
                <div className="relative flex-1">
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    className="absolute left-3 top-2.5 h-4 w-4 text-txt-muted"
                    aria-hidden="true"
                  >
                    <circle cx="11" cy="11" r="8" />
                    <line x1="21" y1="21" x2="16.65" y2="16.65" />
                  </svg>
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Search conversations..."
                    className="w-full rounded-full border border-white/40 bg-white/40 pl-9 pr-8 py-2 text-xs sm:text-sm text-txt-primary placeholder:text-txt-muted outline-none focus:bg-white/70 focus:border-brand/50 shadow-xs backdrop-blur-xs transition-all"
                  />
                  {searchQuery && (
                    <button
                      type="button"
                      onClick={() => setSearchQuery('')}
                      className="absolute right-3 top-2.5 text-xs text-txt-muted hover:text-txt-primary"
                      aria-label="Clear search"
                    >
                      ✕
                    </button>
                  )}
                </div>

                <button
                  type="button"
                  onClick={() => setIsNewChatOpen(true)}
                  title="New conversation"
                  aria-label="New conversation"
                  className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-white/40 bg-white/40 text-txt-secondary hover:bg-white/75 hover:text-brand transition-all shadow-xs backdrop-blur-sm"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4">
                    <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                    <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
                  </svg>
                </button>
              </div>
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto">
              <ConversationList
                conversations={filteredConversations}
                selectedId={selectedConversation?.id}
                onSelect={handleSelectConversation}
                isLoading={isLoadingConversations}
                error={conversationError}
                activityState={activityState}
              />
            </div>
          </>
        ) : (
          /* Organization Channels Sidebar */
          <ChannelList
            organization={activeWorkspace}
            channels={channels}
            selectedId={selectedConversation?.id}
            onSelect={handleSelectConversation}
            isLoading={isLoadingChannels}
            error={channelError}
            onOpenCreateChannel={() => setIsCreateChannelOpen(true)}
            onRetry={() => {
              if (activeWorkspace) {
                setIsLoadingChannels(true)
                getOrgConversations(activeWorkspace.organization_id)
                  .then((res) => setChannels(sortByNewestActivity(res, activityStateRef.current)))
                  .catch((err) => setChannelError(formatError(err, 'Unable to load channels.')))
                  .finally(() => setIsLoadingChannels(false))
              }
            }}
            activityState={activityState}
          />
        )}
      </aside>

      {/* Chat Window */}
      <main className={`min-w-0 flex-1 flex-col bg-white/5 backdrop-blur-xs ${selectedConversation ? 'flex' : 'hidden sm:flex'}`}>
        {selectedConversation ? (
          <>
            <header className="flex items-center justify-between border-b border-white/30 bg-white/35 backdrop-blur-xl px-3.5 py-2.5 sm:px-6 sm:py-3.5">
              <div className="flex items-center gap-2.5 sm:gap-3 min-w-0 flex-1">
                {/* Back button on mobile */}
                <button
                  type="button"
                  onClick={() => handleSelectConversation(null)}
                  className="sm:hidden -ml-1 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-txt-muted hover:bg-brand-soft hover:text-brand active:bg-brand-selected"
                  aria-label="Back to conversations"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" className="h-5 w-5">
                    <polyline points="15 18 9 12 15 6" />
                  </svg>
                </button>
                <div className="relative shrink-0">
                  <span className="grid h-10 w-10 place-items-center rounded-2xl bg-teal-600/90 font-bold text-white shadow-xs">
                    {isOrgChannel ? '#' : (participantLabel.charAt(0).toUpperCase())}
                  </span>
                </div>
                <div className="min-w-0 flex-1">
                  <h2 className="font-bold text-sm sm:text-base text-txt-primary truncate leading-tight">
                    {participantLabel}
                  </h2>
                  <p className="text-[11px] sm:text-xs text-txt-muted truncate leading-tight mt-0.5">
                    {descriptionLabel}
                  </p>
                </div>
              </div>
              <div className="shrink-0 flex items-center gap-1.5 sm:gap-2 pl-2 text-txt-secondary">
                {/* Video action */}
                <button
                  type="button"
                  title="Video call"
                  aria-label="Video call"
                  className="flex h-8 w-8 sm:h-9 sm:w-9 items-center justify-center rounded-xl hover:bg-white/60 hover:text-brand transition-all"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4 sm:h-4.5 sm:w-4.5">
                    <polygon points="23 7 16 12 23 17 23 7" />
                    <rect x="1" y="5" width="15" height="14" rx="2" ry="2" />
                  </svg>
                </button>

                {/* Audio call action */}
                <button
                  type="button"
                  title="Voice call"
                  aria-label="Voice call"
                  className="flex h-8 w-8 sm:h-9 sm:w-9 items-center justify-center rounded-xl hover:bg-white/60 hover:text-brand transition-all"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4 sm:h-4.5 sm:w-4.5">
                    <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z" />
                  </svg>
                </button>

                {/* More options */}
                <button
                  type="button"
                  title="More options"
                  aria-label="More options"
                  className="flex h-8 w-8 sm:h-9 sm:w-9 items-center justify-center rounded-xl hover:bg-white/60 hover:text-brand transition-all"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4 sm:h-4.5 sm:w-4.5">
                    <circle cx="12" cy="12" r="1" />
                    <circle cx="12" cy="5" r="1" />
                    <circle cx="12" cy="19" r="1" />
                  </svg>
                </button>
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
              disabled={isLoadingMessages || messagesConversationId !== selectedConversation.id}
            />
          </>
        ) : (
          <div className="m-auto px-6 sm:px-8 text-center">
            <div className="mx-auto grid h-16 w-16 place-items-center rounded-3xl bg-white/40 p-2.5 backdrop-blur-md border border-white/50 shadow-sm" aria-hidden="true">
              <ChatProSymbol size={40} glow />
            </div>
            <h2 className="mt-4 sm:mt-5 text-xl sm:text-2xl font-bold text-txt-primary font-display">
              {activeWorkspace ? `Welcome to ${activeWorkspace.organization_name}` : 'Choose a conversation'}
            </h2>
            <p className="mt-2 max-w-sm text-xs sm:text-sm leading-relaxed text-txt-muted">
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
