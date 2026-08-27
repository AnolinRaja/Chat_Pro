export function validateEmail(email) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)
}

export function validateLogin({ email, password }) {
  if (!email || !validateEmail(email)) return 'Enter a valid email address.'
  if (!password) return 'Enter your password.'
  return ''
}

export function validateRegistration({ name, email, password }) {
  if (!name.trim()) return 'Enter your name.'
  if (!email || !validateEmail(email)) return 'Enter a valid email address.'
  if (password.trim().length < 8) return 'Password must be at least 8 characters.'
  return ''
}
