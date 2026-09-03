import api from './api.js'

export async function get2SVStatus() {
  const response = await api.get('/auth/2sv/status')
  return response.data
}

export async function setup2SV() {
  const response = await api.post('/auth/2sv/setup')
  return response.data
}

export async function confirm2SV(code) {
  const response = await api.post('/auth/2sv/confirm', { code })
  return response.data
}

export async function disable2SV(password, code) {
  const response = await api.post('/auth/2sv/disable', { password, code })
  return response.data
}
