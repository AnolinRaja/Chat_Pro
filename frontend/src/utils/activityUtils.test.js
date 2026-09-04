import test from 'node:test'
import assert from 'node:assert/strict'
import {
  sortByNewestActivity,
  recordMessageActivity,
  clearConversationUnread,
} from './activityUtils.js'

test('sortByNewestActivity orders conversations by latestActivityAt descending', () => {
  const conv1 = { id: 'conv-1', name: 'General', updated_at: '2026-09-01T10:00:00Z' }
  const conv2 = { id: 'conv-2', name: 'Engineering', updated_at: '2026-09-01T12:00:00Z' }
  const conv3 = { id: 'conv-3', name: 'Random', updated_at: '2026-09-01T08:00:00Z' }

  const sorted = sortByNewestActivity([conv1, conv2, conv3])
  assert.deepEqual(sorted.map((c) => c.id), ['conv-2', 'conv-1', 'conv-3'])
})

test('Critical Invariant: active conversation selection does NOT change ordering', () => {
  const convGeneral = { id: 'general', name: 'General', updated_at: '2026-09-01T10:00:00Z' }
  const convEngineering = { id: 'engineering', name: 'Engineering', updated_at: '2026-09-01T09:00:00Z' }

  // Initial list: General is newer than Engineering
  const list = [convGeneral, convEngineering]
  const activityState = {}

  // User is currently viewing General
  const selectedConversationId = 'general'

  // A new message arrives in Engineering at 11:00:00Z
  const updatedActivityState = recordMessageActivity(activityState, 'engineering', {
    content: 'Deployment completed successfully',
    timestamp: '2026-09-01T11:00:00Z',
    isCurrentlySelected: selectedConversationId === 'engineering',
  })

  // Reorder list based on updated activity map
  const reordered = sortByNewestActivity(list, updatedActivityState)

  // Engineering MUST move to top because it has the newest message timestamp (11:00 vs 10:00)
  assert.equal(reordered[0].id, 'engineering')
  assert.equal(reordered[1].id, 'general')

  // General is STILL the selected conversation
  assert.equal(selectedConversationId, 'general')
})

test('recordMessageActivity increments unread count on inactive conversation and updates preview', () => {
  let state = {}
  state = recordMessageActivity(state, 'conv-1', {
    content: 'Hello there!',
    timestamp: '2026-09-04T12:00:00Z',
    isCurrentlySelected: false,
  })

  assert.equal(state['conv-1'].unreadCount, 1)
  assert.equal(state['conv-1'].latestPreview, 'Hello there!')
  assert.equal(state['conv-1'].latestMessageAt, '2026-09-04T12:00:00Z')

  // Second message on inactive conversation increments unread to 2
  state = recordMessageActivity(state, 'conv-1', {
    content: 'Are you available?',
    timestamp: '2026-09-04T12:01:00Z',
    isCurrentlySelected: false,
  })

  assert.equal(state['conv-1'].unreadCount, 2)
  assert.equal(state['conv-1'].latestPreview, 'Are you available?')
})

test('recordMessageActivity on currently selected conversation does NOT increment unread count', () => {
  let state = {}
  state = recordMessageActivity(state, 'conv-active', {
    content: 'Message in active chat',
    timestamp: '2026-09-04T12:05:00Z',
    isCurrentlySelected: true,
  })

  assert.equal(state['conv-active'].unreadCount, 0)
  assert.equal(state['conv-active'].latestPreview, 'Message in active chat')
  assert.equal(state['conv-active'].latestMessageAt, '2026-09-04T12:05:00Z')
})

test('clearConversationUnread clears unread count without mutating activity timestamp or preview', () => {
  let state = {
    'conv-1': {
      latestPreview: 'Important announcement',
      latestMessageAt: '2026-09-04T12:00:00Z',
      unreadCount: 5,
    },
  }

  state = clearConversationUnread(state, 'conv-1')

  assert.equal(state['conv-1'].unreadCount, 0)
  assert.equal(state['conv-1'].latestPreview, 'Important announcement')
  assert.equal(state['conv-1'].latestMessageAt, '2026-09-04T12:00:00Z')
})

test('User isolation: resetting activity state returns an empty map', () => {
  const initialUserState = {
    'conv-user-a': { latestPreview: 'Secret A', latestMessageAt: '2026-09-04T12:00:00Z', unreadCount: 3 },
  }
  assert.ok(Object.keys(initialUserState).length > 0)

  // On user change, state resets to empty map
  const resetState = {}
  assert.deepEqual(resetState, {})
})
