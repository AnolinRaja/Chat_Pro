/**
 * ChatPRO User-Scoped Persistent UI Session Storage
 * 
 * Provides safe, user-scoped persistence for non-sensitive UI context
 * (last active organization and conversation ID).
 * 
 * SECURITY RULE:
 * NEVER store tokens, passwords, OTP secrets, user models, or message data here.
 * LocalStorage data is treated strictly as untrusted UI hints.
 */

const STORAGE_PREFIX = 'chatpro:last_session:'

function getStorageKey(userId) {
  if (!userId || typeof userId !== 'string') return null
  return `${STORAGE_PREFIX}${userId.trim()}`
}

export function getSavedChatContext(userId) {
  const key = getStorageKey(userId)
  if (!key) {
    return { organizationId: null, conversationId: null }
  }

  try {
    const raw = localStorage.getItem(key)
    if (!raw) {
      return { organizationId: null, conversationId: null }
    }

    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return { organizationId: null, conversationId: null }
    }

    const organizationId = typeof parsed.organizationId === 'string' && parsed.organizationId.trim()
      ? parsed.organizationId.trim()
      : null

    const conversationId = typeof parsed.conversationId === 'string' && parsed.conversationId.trim()
      ? parsed.conversationId.trim()
      : null

    return { organizationId, conversationId }
  } catch {
    // Handle blocked localStorage, disabled cookies, or malformed JSON gracefully
    return { organizationId: null, conversationId: null }
  }
}

export function saveChatContext(userId, context = {}) {
  const key = getStorageKey(userId)
  if (!key) return

  try {
    const organizationId = typeof context.organizationId === 'string' && context.organizationId.trim()
      ? context.organizationId.trim()
      : null

    const conversationId = typeof context.conversationId === 'string' && context.conversationId.trim()
      ? context.conversationId.trim()
      : null

    const payload = { organizationId, conversationId }
    localStorage.setItem(key, JSON.stringify(payload))
  } catch {
    // Gracefully ignore storage write failures (e.g. quota exceeded, Incognito restrictions)
  }
}

export function clearSavedChatContext(userId) {
  const key = getStorageKey(userId)
  if (!key) return

  try {
    localStorage.removeItem(key)
  } catch {
    // Gracefully ignore storage removal failures
  }
}
