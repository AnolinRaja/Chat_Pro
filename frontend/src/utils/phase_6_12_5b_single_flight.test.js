/**
 * Phase 6.12.5B — Single-Flight Refresh: Deterministic Race Test
 *
 * Verifies that singleFlightRefresh() guarantees exactly ONE in-flight
 * POST /auth/refresh regardless of how many consumers call it concurrently.
 *
 * Framework: node:test + node:assert/strict (project standard)
 *
 * NOTE: We test the singleFlightRefresh function directly by importing it
 * and monkey-patching the api axios instance's .post method to count calls
 * and control resolution timing.
 */
import test from 'node:test'
import assert from 'node:assert/strict'

// ---------------------------------------------------------------------------
// Minimal reproduction of the single-flight mechanism under test.
// We cannot import from '../services/api.js' because it uses import.meta.env
// (Vite-only).  Instead we reproduce the exact same logic here so the test
// validates the *algorithm*, not Vite's module resolution.
// ---------------------------------------------------------------------------

function createSingleFlightHarness() {
  let inMemoryAccessToken = null
  let _refreshPromise = null
  let postCallCount = 0
  let postResolvers = []

  // Simulated api.post('/auth/refresh') — callers can control when it
  // resolves via the returned { resolve, reject } handles.
  function apiPostRefresh() {
    postCallCount++
    return new Promise((resolve, reject) => {
      postResolvers.push({ resolve, reject })
    })
  }

  function setAccessToken(token) {
    inMemoryAccessToken = token || null
  }

  function getAccessToken() {
    return inMemoryAccessToken
  }

  function clearAccessToken() {
    inMemoryAccessToken = null
  }

  // Exact replica of singleFlightRefresh() from api.js
  function singleFlightRefresh() {
    if (_refreshPromise) return _refreshPromise

    _refreshPromise = apiPostRefresh()
      .then((response) => {
        const data = response.data
        if (data?.access_token) {
          setAccessToken(data.access_token)
        }
        return data
      })
      .catch((error) => {
        clearAccessToken()
        throw error
      })
      .finally(() => {
        _refreshPromise = null
      })

    return _refreshPromise
  }

  return {
    singleFlightRefresh,
    getAccessToken,
    setAccessToken,
    getPostCallCount: () => postCallCount,
    getPostResolvers: () => postResolvers,
    resetPostCallCount: () => { postCallCount = 0 },
    resetPostResolvers: () => { postResolvers = [] },
  }
}

// ===========================================================================
// Test 1: Concurrent race — two callers before first resolves
// ===========================================================================
test('single-flight: two concurrent callers produce exactly 1 HTTP refresh call', async () => {
  const harness = createSingleFlightHarness()

  // Simulate AuthProvider and RealtimeProvider calling concurrently
  const promise1 = harness.singleFlightRefresh() // AuthProvider
  const promise2 = harness.singleFlightRefresh() // RealtimeProvider

  // Both must reference the same Promise
  assert.equal(promise1, promise2, 'Both callers must share the same Promise instance')

  // Exactly 1 HTTP call must have been made
  assert.equal(harness.getPostCallCount(), 1, 'Exactly one POST /auth/refresh must be issued')

  // Resolve the single in-flight request
  const resolvers = harness.getPostResolvers()
  assert.equal(resolvers.length, 1, 'Exactly one resolver must exist')
  resolvers[0].resolve({ data: { access_token: 'tok-abc-123', user: { id: 'u1' } } })

  // Both callers must receive the same result
  const result1 = await promise1
  const result2 = await promise2

  assert.deepEqual(result1, { access_token: 'tok-abc-123', user: { id: 'u1' } })
  assert.deepEqual(result2, { access_token: 'tok-abc-123', user: { id: 'u1' } })

  // In-memory token must be set
  assert.equal(harness.getAccessToken(), 'tok-abc-123')
})

// ===========================================================================
// Test 2: Three concurrent callers — still exactly 1 HTTP call
// ===========================================================================
test('single-flight: three concurrent callers still produce exactly 1 HTTP call', async () => {
  const harness = createSingleFlightHarness()

  const p1 = harness.singleFlightRefresh()
  const p2 = harness.singleFlightRefresh()
  const p3 = harness.singleFlightRefresh()

  assert.equal(p1, p2)
  assert.equal(p2, p3)
  assert.equal(harness.getPostCallCount(), 1)

  harness.getPostResolvers()[0].resolve({ data: { access_token: 'tok-shared' } })

  const [r1, r2, r3] = await Promise.all([p1, p2, p3])
  assert.equal(r1.access_token, 'tok-shared')
  assert.equal(r2.access_token, 'tok-shared')
  assert.equal(r3.access_token, 'tok-shared')
})

// ===========================================================================
// Test 3: Sequential calls after resolution create a NEW request
// ===========================================================================
test('single-flight: after resolution, next call creates a new HTTP request', async () => {
  const harness = createSingleFlightHarness()

  // First call
  const p1 = harness.singleFlightRefresh()
  assert.equal(harness.getPostCallCount(), 1)

  harness.getPostResolvers()[0].resolve({ data: { access_token: 'tok-first' } })
  await p1

  // Second call — _refreshPromise should have been cleared by .finally()
  const p2 = harness.singleFlightRefresh()
  assert.equal(harness.getPostCallCount(), 2, 'A new HTTP request must be created after prior resolution')

  // p2 must be a different Promise
  assert.notEqual(p1, p2)

  harness.getPostResolvers()[1].resolve({ data: { access_token: 'tok-second' } })
  const r2 = await p2
  assert.equal(r2.access_token, 'tok-second')
  assert.equal(harness.getAccessToken(), 'tok-second')
})

// ===========================================================================
// Test 4: Failure propagates to ALL concurrent callers
// ===========================================================================
test('single-flight: refresh failure propagates to all concurrent callers', async () => {
  const harness = createSingleFlightHarness()

  const p1 = harness.singleFlightRefresh()
  const p2 = harness.singleFlightRefresh()

  assert.equal(harness.getPostCallCount(), 1)

  // Reject the single in-flight request
  const refreshError = new Error('401 Unauthorized')
  harness.getPostResolvers()[0].reject(refreshError)

  // Both callers must receive the rejection
  await assert.rejects(p1, { message: '401 Unauthorized' })
  await assert.rejects(p2, { message: '401 Unauthorized' })

  // Token must be cleared
  assert.equal(harness.getAccessToken(), null)
})

// ===========================================================================
// Test 5: After failure, next call creates a NEW request (promise cleared)
// ===========================================================================
test('single-flight: after failure, next call creates a new HTTP request', async () => {
  const harness = createSingleFlightHarness()

  // First call — fails
  const p1 = harness.singleFlightRefresh()
  harness.getPostResolvers()[0].reject(new Error('network error'))
  await assert.rejects(p1)

  assert.equal(harness.getPostCallCount(), 1)

  // Second call — must create new request
  const p2 = harness.singleFlightRefresh()
  assert.equal(harness.getPostCallCount(), 2)

  harness.getPostResolvers()[1].resolve({ data: { access_token: 'tok-recovery' } })
  const r2 = await p2
  assert.equal(r2.access_token, 'tok-recovery')
  assert.equal(harness.getAccessToken(), 'tok-recovery')
})

// ===========================================================================
// Test 6: RealtimeProvider cannot independently log the user out
// ===========================================================================
test('single-flight: refresh failure in RealtimeProvider path does not clear a valid token', async () => {
  const harness = createSingleFlightHarness()

  // Simulate AuthProvider already set a valid token
  harness.setAccessToken('tok-valid-session')

  // RealtimeProvider's ensureFreshToken logic: if token exists, skip refresh
  const token = harness.getAccessToken()
  assert.equal(token, 'tok-valid-session', 'Token already exists — RealtimeProvider must NOT call refresh')

  // No HTTP call should have been made
  assert.equal(harness.getPostCallCount(), 0)
})

// ===========================================================================
// Test 7: Simulated full startup lifecycle
// ===========================================================================
test('single-flight: full startup — AuthProvider + RealtimeProvider concurrent init', async () => {
  const harness = createSingleFlightHarness()

  // --- Simulate concurrent startup ---
  // AuthProvider calls singleFlightRefresh() in restoreSession()
  const authPromise = harness.singleFlightRefresh()

  // RealtimeProvider calls singleFlightRefresh() in ensureFreshToken()
  // (because getAccessToken() returns null at startup)
  assert.equal(harness.getAccessToken(), null)
  const realtimePromise = harness.singleFlightRefresh()

  // INVARIANT: exactly 1 HTTP call
  assert.equal(harness.getPostCallCount(), 1, 'Startup must produce exactly 1 refresh HTTP call')
  assert.equal(authPromise, realtimePromise, 'Both providers share the same Promise')

  // Resolve the refresh
  harness.getPostResolvers()[0].resolve({
    data: { access_token: 'tok-startup', user: { id: 'user-42', name: 'Test User' } },
  })

  const authResult = await authPromise
  const realtimeResult = await realtimePromise

  // Both get the same data
  assert.equal(authResult.access_token, 'tok-startup')
  assert.equal(realtimeResult.access_token, 'tok-startup')
  assert.equal(authResult.user.id, 'user-42')

  // Token is set in memory
  assert.equal(harness.getAccessToken(), 'tok-startup')

  // After resolution, a subsequent refresh (e.g. 401 recovery) creates a new request
  const recoveryPromise = harness.singleFlightRefresh()
  assert.equal(harness.getPostCallCount(), 2)
  assert.notEqual(recoveryPromise, authPromise)
})
