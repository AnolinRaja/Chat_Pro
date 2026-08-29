import api from './api.js'

export async function verifyRegistration(email, otp) {
  const response = await api.post('/auth/register/verify', { email, otp })
  return response.data
}

export async function resendRegistration(email) {
  const response = await api.post('/auth/register/resend', { email })
  return response.data
}

export async function verifyLogin(email, otp) {
  const response = await api.post('/auth/login/verify', { email, otp })
  return response.data
}

export async function resendLogin(email) {
  const response = await api.post('/auth/login/resend', { email })
  return response.data
}

export async function requestPasswordReset(email) {
  const response = await api.post('/auth/forgot-password/request', { email })
  return response.data
}

export async function verifyPasswordReset(email, otp) {
  const response = await api.post('/auth/forgot-password/verify', { email, otp })
  return response.data
}

export async function completePasswordReset(resetToken, newPassword) {
  const response = await api.post('/auth/forgot-password/reset', {
    reset_token: resetToken,
    new_password: newPassword,
  })
  return response.data
}
