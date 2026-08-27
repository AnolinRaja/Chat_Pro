import api from './api.js'

export async function searchUsers(query) {
  const response = await api.get('/users/search', { params: { q: query } })
  return response.data.users
}

export async function getConversations() {
  const response = await api.get('/conversations')
  return response.data
}

export async function createConversation(otherUserId) {
  const response = await api.post('/conversations', { other_user_id: otherUserId })
  return response.data
}

export async function getMessages(conversationId, { limit = 50, cursor } = {}) {
  const response = await api.get(`/conversations/${conversationId}/messages`, {
    params: { limit, ...(cursor ? { cursor } : {}) },
  })
  return { messages: response.data, nextCursor: response.headers['x-next-cursor'] || null }
}

export async function sendMessage(conversationId, content) {
  const response = await api.post(`/conversations/${conversationId}/messages`, { content })
  return response.data
}
