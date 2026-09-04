/**
 * Activity state helper functions for Phase 6.12.3: Chat-First Conversation Activity
 */

/**
 * Sorts an array of conversations (DMs or channels) descending strictly by their newest activity timestamp.
 *
 * @param {Array} items
 * @param {Object} activityMap
 * @returns {Array}
 */
export function sortByNewestActivity(items = [], activityMap = {}) {
  return [...items].sort((a, b) => {
    const timeA = new Date(activityMap[a.id]?.latestMessageAt || a.updated_at || a.created_at || 0).getTime()
    const timeB = new Date(activityMap[b.id]?.latestMessageAt || b.updated_at || b.created_at || 0).getTime()
    return timeB - timeA
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
 * @param {boolean} params.isCurrentlySelected
 * @returns {Object}
 */
export function recordMessageActivity(currentActivityState, conversationId, { content, timestamp, isCurrentlySelected }) {
  if (!conversationId) return currentActivityState

  const existing = currentActivityState[conversationId] || {}
  const currentUnread = existing.unreadCount || 0
  const unreadCount = isCurrentlySelected ? 0 : currentUnread + 1
  const latestMessageAt = timestamp || new Date().toISOString()

  return {
    ...currentActivityState,
    [conversationId]: {
      latestPreview: content,
      latestMessageAt,
      unreadCount,
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
    },
  }
}
