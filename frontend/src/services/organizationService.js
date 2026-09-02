import api from './api.js'

export async function getMyOrganizations() {
  try {
    const response = await api.get('/organizations/my')
    return response.data
  } catch (error) {
    if (error.response?.status === 404) {
      const fallbackResponse = await api.get('/auth/organizations/status')
      return fallbackResponse.data
    }
    throw error
  }
}

export async function joinOrganization({ orgId, joinCode }) {
  const payload = {
    org_id: orgId.trim().toLowerCase(),
    join_code: joinCode.trim(),
  }

  try {
    const response = await api.post('/organizations/join', payload)
    return response.data
  } catch (error) {
    if (error.response?.status === 404 && error.response?.data?.detail !== 'Organization not found.') {
      const fallbackResponse = await api.post('/auth/organizations/join', payload)
      return fallbackResponse.data
    }
    throw error
  }
}

export async function getOrgConversations(organizationId) {
  const response = await api.get(`/organizations/${organizationId}/conversations`)
  return response.data
}

export async function createOrgConversation(organizationId, { name, description = '' }) {
  const response = await api.post(`/organizations/${organizationId}/conversations`, {
    name: name.trim().toLowerCase(),
    description: description.trim(),
  })
  return response.data
}
