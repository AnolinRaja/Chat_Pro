/**
 * Formats a date into a compact relative time string:
 * - 'Just now' (< 1 minute)
 * - '2m', '18m' (< 60 minutes)
 * - '2h', '5h' (< 24 hours)
 * - 'Yesterday' (between 24h and 48h ago, or previous calendar day)
 * - 'Mon', 'Tue', etc. (within last 7 days)
 * - 'Jan 12' or localized short date (older)
 * Handles null/undefined/malformed dates safely.
 *
 * @param {string | Date | null | undefined} dateInput
 * @returns {string}
 */
export function formatRelativeTime(dateInput) {
  if (!dateInput) return ''
  const date = dateInput instanceof Date ? dateInput : new Date(dateInput)
  if (Number.isNaN(date.getTime())) return ''

  const now = new Date()
  const diffMs = now.getTime() - date.getTime()

  // Future timestamp or tiny clock skew
  if (diffMs < 60 * 1000) {
    return 'Just now'
  }

  const diffMinutes = Math.floor(diffMs / (60 * 1000))
  if (diffMinutes < 60) {
    return `${diffMinutes}m`
  }

  const diffHours = Math.floor(diffMs / (3600 * 1000))
  if (diffHours < 24) {
    return `${diffHours}h`
  }

  // Check if yesterday
  const yesterday = new Date(now)
  yesterday.setDate(now.getDate() - 1)
  const isSameDay = (d1, d2) =>
    d1.getFullYear() === d2.getFullYear() &&
    d1.getMonth() === d2.getMonth() &&
    d1.getDate() === d2.getDate()

  if (isSameDay(date, yesterday)) {
    return 'Yesterday'
  }

  const diffDays = Math.floor(diffMs / (24 * 3600 * 1000))
  if (diffDays < 7) {
    return date.toLocaleDateString(undefined, { weekday: 'short' })
  }

  // Older: e.g. "Oct 14" or "Oct 14, 25"
  const currentYear = now.getFullYear()
  if (date.getFullYear() === currentYear) {
    return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
  }

  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: '2-digit' })
}

/**
 * Returns a full localized timestamp for accessible tooltips (e.g. title attribute).
 *
 * @param {string | Date | null | undefined} dateInput
 * @returns {string}
 */
export function formatFullTimestamp(dateInput) {
  if (!dateInput) return ''
  const date = dateInput instanceof Date ? dateInput : new Date(dateInput)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString()
}
