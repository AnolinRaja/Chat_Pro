import test from 'node:test'
import assert from 'node:assert/strict'
import { formatRelativeTime, formatFullTimestamp } from './dateUtils.js'

test('formatRelativeTime handles null, undefined, empty, and invalid dates safely', () => {
  assert.equal(formatRelativeTime(null), '')
  assert.equal(formatRelativeTime(undefined), '')
  assert.equal(formatRelativeTime(''), '')
  assert.equal(formatRelativeTime('invalid-date-string'), '')
})

test('formatRelativeTime formats timestamps under 1 minute as "Just now"', () => {
  const now = new Date()
  assert.equal(formatRelativeTime(now), 'Just now')

  const thirtySecondsAgo = new Date(now.getTime() - 30 * 1000)
  assert.equal(formatRelativeTime(thirtySecondsAgo), 'Just now')

  const slightFuture = new Date(now.getTime() + 10 * 1000)
  assert.equal(formatRelativeTime(slightFuture), 'Just now')
})

test('formatRelativeTime formats minutes correctly', () => {
  const now = new Date()
  const fiveMinutesAgo = new Date(now.getTime() - 5 * 60 * 1000)
  assert.equal(formatRelativeTime(fiveMinutesAgo), '5m')

  const fiftyNineMinutesAgo = new Date(now.getTime() - 59 * 60 * 1000)
  assert.equal(formatRelativeTime(fiftyNineMinutesAgo), '59m')
})

test('formatRelativeTime formats hours correctly', () => {
  const now = new Date()
  const twoHoursAgo = new Date(now.getTime() - 2 * 3600 * 1000)
  assert.equal(formatRelativeTime(twoHoursAgo), '2h')

  const twentyThreeHoursAgo = new Date(now.getTime() - 23 * 3600 * 1000)
  assert.equal(formatRelativeTime(twentyThreeHoursAgo), '23h')
})

test('formatRelativeTime formats yesterday correctly', () => {
  const now = new Date()
  const yesterday = new Date(now)
  yesterday.setDate(now.getDate() - 1)
  // Set to noon yesterday to ensure same day
  yesterday.setHours(12, 0, 0, 0)
  assert.equal(formatRelativeTime(yesterday), 'Yesterday')
})

test('formatRelativeTime formats weekdays within 7 days', () => {
  const now = new Date()
  const fourDaysAgo = new Date(now.getTime() - 4 * 24 * 3600 * 1000)
  const formatted = formatRelativeTime(fourDaysAgo)
  assert.ok(formatted.length >= 3)
})

test('formatFullTimestamp returns localized timestamp or empty string', () => {
  assert.equal(formatFullTimestamp(null), '')
  assert.equal(formatFullTimestamp('invalid'), '')
  const d = new Date('2026-09-01T12:00:00Z')
  assert.ok(formatFullTimestamp(d).length > 0)
})
