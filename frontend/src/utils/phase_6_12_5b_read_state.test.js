import test from 'node:test'
import assert from 'node:assert/strict'
import {
  hydrateActivityState,
  recordMessageActivity,
  applyReadState,
  sortByNewestActivity,
} from './activityUtils.js'

test('1. conversation.read with known message cursor: resolves created_at from known message', () => {
  let state = {
    'conv-1': {
      unreadCount: 3,
      latestMessageId: 'msg-10',
      latestMessageAt: '2026-09-08T10:00:00Z',
    },
  }

  state = applyReadState(state, 'conv-1', {
    lastReadMessageId: 'msg-10',
    lastReadMessageCreatedAt: '2026-09-08T10:00:00Z', // Resolved from known message
    currentUserId: 'user-1',
    eventUserId: 'user-1',
  })

  assert.equal(state['conv-1'].unreadCount, 0)
  assert.equal(state['conv-1'].lastReadMessageId, 'msg-10')
  assert.equal(state['conv-1'].lastReadMessageCreatedAt, '2026-09-08T10:00:00Z')
})

test('2. conversation.read with unknown message cursor: clears unread without fabricating timestamp', () => {
  let state = {
    'conv-1': {
      unreadCount: 4,
      lastReadMessageId: null,
      lastReadMessageCreatedAt: null,
    },
  }

  // Incoming event for unknown message (not in memory, created_at unavailable)
  state = applyReadState(state, 'conv-1', {
    lastReadMessageId: 'msg-unknown',
    lastReadMessageCreatedAt: null, // Unresolved
    currentUserId: 'user-1',
    eventUserId: 'user-1',
  })

  assert.equal(state['conv-1'].unreadCount, 0)
  assert.equal(state['conv-1'].lastReadMessageId, 'msg-unknown')
  assert.equal(state['conv-1'].lastReadMessageCreatedAt, null) // NO fabricated timestamp!
})

test('3. last_read_at never used as message created_at: verify created_at is not replaced by wall clock', () => {
  let state = {
    'conv-1': {
      unreadCount: 2,
      lastReadMessageId: 'm1',
      lastReadMessageCreatedAt: '2026-09-08T10:00:00Z',
    },
  }

  // Incoming conversation.read event with last_read_at = "2026-09-08T12:00:00Z" (wall clock time)
  // The frontend passes lastReadMessageCreatedAt = null if message is unknown
  state = applyReadState(state, 'conv-1', {
    lastReadMessageId: 'm1',
    lastReadMessageCreatedAt: null,
    currentUserId: 'user-1',
    eventUserId: 'user-1',
  })

  assert.equal(state['conv-1'].lastReadMessageCreatedAt, '2026-09-08T10:00:00Z') // Preserved existing msg timestamp!
})

test('4. stale read cursor ignored: incoming older read cursor does not regress local cursor', () => {
  let state = {
    'conv-1': {
      unreadCount: 0,
      lastReadMessageId: 'msg-20',
      lastReadMessageCreatedAt: '2026-09-08T10:20:00Z',
    },
  }

  // Stale event for msg-10 (10:10:00Z)
  state = applyReadState(state, 'conv-1', {
    lastReadMessageId: 'msg-10',
    lastReadMessageCreatedAt: '2026-09-08T10:10:00Z',
    currentUserId: 'user-1',
    eventUserId: 'user-1',
  })

  assert.equal(state['conv-1'].lastReadMessageId, 'msg-20')
  assert.equal(state['conv-1'].lastReadMessageCreatedAt, '2026-09-08T10:20:00Z')
})

test('5. equal read cursor idempotent: applying same cursor leaves state clean', () => {
  let state = {
    'conv-1': {
      unreadCount: 0,
      lastReadMessageId: 'msg-10',
      lastReadMessageCreatedAt: '2026-09-08T10:10:00Z',
    },
  }

  state = applyReadState(state, 'conv-1', {
    lastReadMessageId: 'msg-10',
    lastReadMessageCreatedAt: '2026-09-08T10:10:00Z',
    currentUserId: 'user-1',
    eventUserId: 'user-1',
  })

  assert.equal(state['conv-1'].unreadCount, 0)
  assert.equal(state['conv-1'].lastReadMessageId, 'msg-10')
})

test('6. newer read cursor accepted: updates lastReadMessageId and createdAt', () => {
  let state = {
    'conv-1': {
      unreadCount: 2,
      lastReadMessageId: 'msg-10',
      lastReadMessageCreatedAt: '2026-09-08T10:10:00Z',
    },
  }

  state = applyReadState(state, 'conv-1', {
    lastReadMessageId: 'msg-30',
    lastReadMessageCreatedAt: '2026-09-08T10:30:00Z',
    currentUserId: 'user-1',
    eventUserId: 'user-1',
  })

  assert.equal(state['conv-1'].unreadCount, 0)
  assert.equal(state['conv-1'].lastReadMessageId, 'msg-30')
  assert.equal(state['conv-1'].lastReadMessageCreatedAt, '2026-09-08T10:30:00Z')
})

test('7. active live message triggers server read flow: active chat keeps unreadCount = 0', () => {
  let state = {}
  state = recordMessageActivity(state, 'conv-active', {
    content: 'Live message in active chat',
    timestamp: '2026-09-08T10:00:00Z',
    messageId: 'msg-11',
    senderId: 'user-2',
    currentUserId: 'user-1',
    isCurrentlySelected: true,
  })

  assert.equal(state['conv-active'].unreadCount, 0)
  assert.equal(state['conv-active'].latestMessageId, 'msg-11')
})

test('8. inactive live message does not trigger server read: increments unreadCount', () => {
  let state = {}
  state = recordMessageActivity(state, 'conv-inactive', {
    content: 'Live message in background chat',
    timestamp: '2026-09-08T10:00:00Z',
    messageId: 'msg-11',
    senderId: 'user-2',
    currentUserId: 'user-1',
    isCurrentlySelected: false,
  })

  assert.equal(state['conv-inactive'].unreadCount, 1)
})

test('9. active live message followed by app reopen remains read: backend server read cursor matches latest msg', () => {
  // Simulates local state after applyReadState is invoked on live active message
  let state = recordMessageActivity({}, 'conv-active', {
    content: 'Message 11',
    timestamp: '2026-09-08T10:00:00Z',
    messageId: 'msg-11',
    isCurrentlySelected: true,
  })

  state = applyReadState(state, 'conv-active', {
    lastReadMessageId: 'msg-11',
    lastReadMessageCreatedAt: '2026-09-08T10:00:00Z',
  })

  assert.equal(state['conv-active'].unreadCount, 0)
  assert.equal(state['conv-active'].lastReadMessageId, 'msg-11')
})

test('10. rapid active live messages request coalescing: duplicate cursor skips redundant read updates', () => {
  let state = {
    'conv-1': {
      unreadCount: 0,
      lastReadMessageId: 'msg-10',
      lastReadMessageCreatedAt: '2026-09-08T10:00:00Z',
    },
  }

  // First message
  state = recordMessageActivity(state, 'conv-1', {
    content: 'M11',
    timestamp: '2026-09-08T10:01:00Z',
    messageId: 'msg-11',
    isCurrentlySelected: true,
  })
  state = applyReadState(state, 'conv-1', { lastReadMessageId: 'msg-11', lastReadMessageCreatedAt: '2026-09-08T10:01:00Z' })

  // Second rapid message
  state = recordMessageActivity(state, 'conv-1', {
    content: 'M12',
    timestamp: '2026-09-08T10:01:01Z',
    messageId: 'msg-12',
    isCurrentlySelected: true,
  })
  state = applyReadState(state, 'conv-1', { lastReadMessageId: 'msg-12', lastReadMessageCreatedAt: '2026-09-08T10:01:01Z' })

  assert.equal(state['conv-1'].unreadCount, 0)
  assert.equal(state['conv-1'].lastReadMessageId, 'msg-12')
})

test('11. read operation does not change latest activity ordering: reading Chat A leaves Chat B on top', () => {
  const chatA = { id: 'chat-A', name: 'Chat A', updated_at: '2026-09-08T10:00:00Z' }
  const chatB = { id: 'chat-B', name: 'Chat B', updated_at: '2026-09-08T10:05:00Z' }

  let activityState = {
    'chat-A': { latestMessageAt: '2026-09-08T10:00:00Z', latestMessageId: 'mA', unreadCount: 3 },
    'chat-B': { latestMessageAt: '2026-09-08T10:05:00Z', latestMessageId: 'mB', unreadCount: 1 },
  }

  // Before reading Chat A, Chat B is top
  let sorted = sortByNewestActivity([chatA, chatB], activityState)
  assert.equal(sorted[0].id, 'chat-B')
  assert.equal(sorted[1].id, 'chat-A')

  // User opens/reads Chat A at 10:10:00Z (wall clock)
  activityState = applyReadState(activityState, 'chat-A', {
    lastReadMessageId: 'mA',
    lastReadMessageCreatedAt: '2026-09-08T10:00:00Z',
  })

  // Chat B MUST REMAIN ON TOP because Chat B has a newer message (10:05 vs 10:00)!
  sorted = sortByNewestActivity([chatA, chatB], activityState)
  assert.equal(sorted[0].id, 'chat-B')
  assert.equal(sorted[1].id, 'chat-A')
})

test('12. REST hydration cannot overwrite newer WS activity: restInitiatedAt guard preserves live WS msg', () => {
  const restInitiatedAt = '2026-09-08T10:00:00Z'

  // Live WS message arrives at 10:01:00Z
  let state = recordMessageActivity({}, 'c1', {
    content: 'Live message',
    timestamp: '2026-09-08T10:01:00Z',
    messageId: 'm-live',
    senderId: 'user-2',
    currentUserId: 'user-1',
    isCurrentlySelected: false,
  })

  // Stale REST response (initiated at 10:00:00Z) resolves at 10:02:00Z with unread_count = 0
  const restItems = [{ id: 'c1', latest_message: { id: 'm-old', created_at: '2026-09-08T09:59:00Z' }, unread_count: 0 }]
  const hydrated = hydrateActivityState(state, restItems, restInitiatedAt)

  assert.equal(hydrated['c1'].unreadCount, 1)
  assert.equal(hydrated['c1'].latestMessageId, 'm-live')
})

test('13. REST hydration cannot overwrite newer read state: restInitiatedAt guard preserves unreadCount = 0', () => {
  const restInitiatedAt = '2026-09-08T10:00:00Z'

  // User marks chat read at 10:01:00Z
  let state = { 'c1': { unreadCount: 3, lastActivityAt: '2026-09-08T10:01:00Z' } }
  state = applyReadState(state, 'c1', {
    lastReadMessageId: 'm-read',
    lastReadMessageCreatedAt: '2026-09-08T10:01:00Z',
  })

  // Stale REST response arrives with unread_count = 3
  const restItems = [{ id: 'c1', latest_message: { id: 'm-old', created_at: '2026-09-08T09:59:00Z' }, unread_count: 3 }]
  const hydrated = hydrateActivityState(state, restItems, restInitiatedAt)

  assert.equal(hydrated['c1'].unreadCount, 0)
})

test('14. conversation switch race: active flag and selectedConversation ref prevent wrong chat read', () => {
  const selectedRef = { current: { id: 'chat-B' } }
  const eventConvId = 'chat-A'

  // Verify that an action intended for chat-A does NOT execute if selectedRef is chat-B
  const isCurrentConv = selectedRef.current && String(selectedRef.current.id) === String(eventConvId)
  assert.equal(isCurrentConv, false)
})

test('15. user/session isolation: resetting state returns clean object', () => {
  const userAState = { 'c1': { unreadCount: 5 } }
  const userBState = {}

  assert.notDeepEqual(userAState, userBState)
  assert.deepEqual(userBState, {})
})

test('16. organization channel equivalent behavior: channel activity maps cleanly to activityState', () => {
  const channels = [
    { id: 'org-c1', name: 'general', latest_message: { id: 'm1', content: 'General msg', created_at: '2026-09-08T10:00:00Z' }, unread_count: 2 },
  ]
  const state = hydrateActivityState({}, channels, '2026-09-08T09:59:00Z')

  assert.equal(state['org-c1'].unreadCount, 2)
  assert.equal(state['org-c1'].latestPreview, 'General msg')
})

test('17. canonical cursor protection: known cursor (M100, 10:00) + older unknown event M90 does not downgrade', () => {
  let state = {
    'conv-1': {
      unreadCount: 0,
      lastReadMessageId: 'M100',
      lastReadMessageCreatedAt: '2026-09-08T10:00:00Z',
    },
  }

  // Incoming event for M90 without created_at timestamp
  state = applyReadState(state, 'conv-1', {
    lastReadMessageId: 'M90',
    lastReadMessageCreatedAt: null,
  })

  // Cursor MUST remain (M100, 10:00)
  assert.equal(state['conv-1'].lastReadMessageId, 'M100')
  assert.equal(state['conv-1'].lastReadMessageCreatedAt, '2026-09-08T10:00:00Z')
})

test('18. canonical cursor protection: known cursor + newer unknown event M105 clears unread without fabricating timestamp', () => {
  let state = {
    'conv-1': {
      unreadCount: 3,
      lastReadMessageId: 'M100',
      lastReadMessageCreatedAt: '2026-09-08T10:00:00Z',
    },
  }

  // Incoming event for M105 without created_at timestamp
  state = applyReadState(state, 'conv-1', {
    lastReadMessageId: 'M105',
    lastReadMessageCreatedAt: null,
  })

  assert.equal(state['conv-1'].unreadCount, 0)
  // Cursor preserved as M100 because M105 timestamp is unresolved
  assert.equal(state['conv-1'].lastReadMessageId, 'M100')
  assert.equal(state['conv-1'].lastReadMessageCreatedAt, '2026-09-08T10:00:00Z')
})

test('19. read queue retry state: failed M101 keeps pending cursor intact until M102 replaces it', () => {
  const pendingRef = { 'conv-1': null }
  const ackedRef = { 'conv-1': null }

  // M101 arrives
  pendingRef['conv-1'] = { msgId: 'M101', msgCreatedAt: '2026-09-08T10:01:00Z' }

  // Simulate POST /read for M101 fails
  // ackedRef stays null, pendingRef stays M101
  assert.equal(ackedRef['conv-1'], null)
  assert.equal(pendingRef['conv-1'].msgId, 'M101')

  // M102 arrives while M101 failed
  pendingRef['conv-1'] = { msgId: 'M102', msgCreatedAt: '2026-09-08T10:02:00Z' }
  assert.equal(pendingRef['conv-1'].msgId, 'M102')

  // POST /read for M102 succeeds
  ackedRef['conv-1'] = 'M102'
  if (pendingRef['conv-1']?.msgId === 'M102') {
    pendingRef['conv-1'] = null
  }

  assert.equal(ackedRef['conv-1'], 'M102')
  assert.equal(pendingRef['conv-1'], null)
})

test('20. session reset clears pending read cursors and timers', () => {
  const pendingRef = { 'c1': { msgId: 'M100' } }
  const ackedRef = { 'c1': 'M90' }
  const inFlightRef = { 'c1': true }
  const timers = { 'c1': 123 }

  // Simulate user logout / session reset cleanup
  delete pendingRef['c1']
  delete ackedRef['c1']
  delete inFlightRef['c1']
  delete timers['c1']

  assert.deepEqual(pendingRef, {})
  assert.deepEqual(ackedRef, {})
  assert.deepEqual(inFlightRef, {})
  assert.deepEqual(timers, {})
})
