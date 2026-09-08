/**
 * Activity state helper functions for Phase 6.12.5B: Frontend Hydration & Multi-Device Read-State Sync
 */

/**
 * Compares two canonical message objects or cursors using (created_at, _id/id).
 * Returns:
 *   > 0 if msgA is newer than msgB
 *   < 0 if msgA is older than msgB
 *     0 if equal / same message
 *
 * @param {Object} msgA
 * @param {Object} msgB
 * @returns {number}
 */
export function compareCanonicalMessages(msgA, msgB) {
  if (!msgA && !msgB) return 0
  if (!msgA) return -1
  if (!msgB) return 1

  const timeA = new Date(msgA.created_at || msgA.createdAt || 0).getTime()
  const timeB = new Date(msgB.created_at || msgB.createdAt || 0).getTime()

  if (timeA !== timeB) {
    return timeA - timeB
  }

  const idA = String(msgA.id || msgA._id || '')
  const idB = String(msgB.id || msgB._id || '')
  return idA.localeCompare(idB)
}

/**
 * Returns true if cursorA is strictly newer than cursorB based on (created_at, id).
 *
 * @param {Object} cursorA
 * @param {Object} cursorB
 * @returns {boolean}
 */
export function isNewerCursor(cursorA, cursorB) {
  return compareCanonicalMessages(cursorA, cursorB) > 0
}

/**
 * Hydrates activityState from REST conversation list items (direct conversations or channels).
 * Enforces REST vs WS / read action race protection using restInitiatedAt.
 *
 * @param {Object} currentActivityState
 * @param {Array} items - List of conversation objects from REST
 * @param {string} restInitiatedAt - ISO string timestamp when REST request was fired
 * @returns {Object} Updated activityState
 */
export function hydrateActivityState(currentActivityState = {}, items = [], restInitiatedAt = null) {
  if (!items || !items.length) return currentActivityState

  const nextState = { ...currentActivityState }
  const reqTime = restInitiatedAt ? new Date(restInitiatedAt).getTime() : 0

  for (const item of items) {
    if (!item || !item.id) continue

    const convId = item.id
    const existing = nextState[convId] || {}
    const restMsg = item.latest_message
    const restUnread = typeof item.unread_count === 'number' ? item.unread_count : 0

    // Compare latest message
    let latestPreview = existing.latestPreview
    let latestMessageAt = existing.latestMessageAt
    let latestMessageId = existing.latestMessageId

    if (restMsg && restMsg.created_at) {
      const restMsgTuple = { created_at: restMsg.created_at, id: restMsg.id }
      const existingMsgTuple = existing.latestMessageAt
        ? { created_at: existing.latestMessageAt, id: existing.latestMessageId }
        : null

      if (!existingMsgTuple || compareCanonicalMessages(restMsgTuple, existingMsgTuple) >= 0) {
        latestPreview = restMsg.content || ''
        latestMessageAt = restMsg.created_at
        latestMessageId = restMsg.id
      }
    } else if (!latestPreview) {
      latestPreview = item.description || 'No messages yet'
      latestMessageAt = item.updated_at || item.created_at || null
      latestMessageId = null
    }

    // Determine unread count precedence:
    // If local activity/read action occurred AFTER restInitiatedAt, preserve local unreadCount
    const localActivityTime = existing.lastActivityAt ? new Date(existing.lastActivityAt).getTime() : 0
    let unreadCount = restUnread

    if (localActivityTime > 0 && reqTime > 0 && localActivityTime > reqTime) {
      unreadCount = typeof existing.unreadCount === 'number' ? existing.unreadCount : restUnread
    }

    nextState[convId] = {
      ...existing,
      latestPreview,
      latestMessageAt,
      latestMessageId,
      unreadCount,
    }
  }

  return nextState
}

/**
 * Sorts an array of conversations (DMs or channels) descending strictly by their newest activity timestamp and canonical message ID.
 *
 * @param {Array} items
 * @param {Object} activityMap
 * @returns {Array}
 */
export function sortByNewestActivity(items = [], activityMap = {}) {
  return [...items].sort((a, b) => {
    const actA = activityMap[a.id]
    const actB = activityMap[b.id]

    const msgA = {
      created_at: actA?.latestMessageAt || a.updated_at || a.created_at || '1970-01-01T00:00:00Z',
      id: actA?.latestMessageId || a.id,
    }
    const msgB = {
      created_at: actB?.latestMessageAt || b.updated_at || b.created_at || '1970-01-01T00:00:00Z',
      id: actB?.latestMessageId || b.id,
    }

    return compareCanonicalMessages(msgB, msgA) // Descending
  })
}

/**
 * Computes the updated activity state for a conversation given an incoming or outgoing message.
 *
 * @param {Object} currentActivityState
 * @param {string} conversationId
 * @param {Object} params
 * @param {string} params.content
 * @param {string|Date} params.timestamp
 * @param {string} [params.messageId]
 * @param {string} [params.senderId]
 * @param {string} [params.currentUserId]
 * @param {boolean} [params.isCurrentlySelected]
 * @returns {Object}
 */
export function recordMessageActivity(
  currentActivityState,
  conversationId,
  {
    content,
    timestamp,
    messageId = null,
    senderId = null,
    currentUserId = null,
    isCurrentlySelected = false,
  }
) {
  if (!conversationId) return currentActivityState

  const existing = currentActivityState[conversationId] || {}
  const currentUnread = typeof existing.unreadCount === 'number' ? existing.unreadCount : 0
  const msgTime = timestamp || new Date().toISOString()

  let unreadCount
  if (isCurrentlySelected) {
    unreadCount = 0
  } else if (senderId && currentUserId && String(senderId) === String(currentUserId)) {
    unreadCount = currentUnread
  } else {
    unreadCount = currentUnread + 1
  }

  return {
    ...currentActivityState,
    [conversationId]: {
      ...existing,
      latestPreview: content,
      latestMessageAt: msgTime,
      latestMessageId: messageId || existing.latestMessageId || null,
      unreadCount,
      lastActivityAt: msgTime,
    },
  }
}

/**
 * Applies a read state update (local user reading, or conversation.read event from multi-device).
 *
 * @param {Object} currentActivityState
 * @param {string} conversationId
 * @param {Object} params
 * @param {string} params.lastReadMessageId
 * @param {string} [params.lastReadMessageCreatedAt]
 * @param {string} [params.currentUserId]
 * @param {string} [params.eventUserId]
 * @returns {Object}
 */
export function applyReadState(
  currentActivityState,
  conversationId,
  {
    lastReadMessageId,
    lastReadMessageCreatedAt = null,
    currentUserId = null,
    eventUserId = null,
  }
) {
  if (!conversationId) return currentActivityState

  // User verification guard
  if (eventUserId && currentUserId && String(eventUserId) !== String(currentUserId)) {
    return currentActivityState
  }

  const existing = currentActivityState[conversationId] || {}

  // If incoming message ID is missing, just clear unread
  if (!lastReadMessageId) {
    return {
      ...currentActivityState,
      [conversationId]: {
        ...existing,
        unreadCount: 0,
      },
    }
  }

  // Canonical Cursor Protection Rule:
  // If an existing known cursor is present (id + createdAt) and incoming event lacks createdAt,
  // DO NOT overwrite or downgrade the existing cursor!
  if (
    existing.lastReadMessageId &&
    existing.lastReadMessageCreatedAt &&
    !lastReadMessageCreatedAt
  ) {
    return {
      ...currentActivityState,
      [conversationId]: {
        ...existing,
        unreadCount: 0,
      },
    }
  }

  // Check if incoming read cursor is stale compared to local read cursor
  // ONLY compare cursors if BOTH existing and incoming cursors have valid timestamps & IDs
  if (
    existing.lastReadMessageId &&
    existing.lastReadMessageCreatedAt &&
    lastReadMessageId &&
    lastReadMessageCreatedAt
  ) {
    const existingCursor = { created_at: existing.lastReadMessageCreatedAt, id: existing.lastReadMessageId }
    const incomingCursor = { created_at: lastReadMessageCreatedAt, id: lastReadMessageId }

    if (compareCanonicalMessages(existingCursor, incomingCursor) > 0) {
      // Existing cursor is strictly newer, ignore stale read event
      return currentActivityState
    }
  }

  // Preserve existing lastReadMessageCreatedAt if incoming timestamp is null/unresolved
  const finalReadId = lastReadMessageId || existing.lastReadMessageId || null
  let finalReadCreatedAt = lastReadMessageCreatedAt || null
  if (!finalReadCreatedAt && finalReadId && finalReadId === existing.lastReadMessageId) {
    finalReadCreatedAt = existing.lastReadMessageCreatedAt || null
  }

  return {
    ...currentActivityState,
    [conversationId]: {
      ...existing,
      unreadCount: 0,
      lastReadMessageId: finalReadId,
      lastReadMessageCreatedAt: finalReadCreatedAt,
      // NOTE: Read operations do NOT modify lastActivityAt or alter conversation activity ordering
    },
  }
}

/**
 * Clears unread count for a selected conversation without modifying its activity timestamp.
 *
 * @param {Object} currentActivityState
 * @param {string} conversationId
 * @returns {Object}
 */
export function clearConversationUnread(currentActivityState, conversationId) {
  if (!conversationId || !currentActivityState[conversationId] || currentActivityState[conversationId].unreadCount === 0) {
    return currentActivityState
  }

  return {
    ...currentActivityState,
    [conversationId]: {
      ...currentActivityState[conversationId],
      unreadCount: 0,
      // NOTE: Read operations do NOT modify lastActivityAt or alter conversation activity ordering
    },
  }
}
