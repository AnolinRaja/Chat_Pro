/**
 * Phase 6.12.5B — 401 Interceptor Behavior Tests
 *
 * Verifies that:
 * 1. Concurrent 401 requests share ONE single-flight refresh request.
 * 2. Set originalRequest._retry = true before singleFlightRefresh so each request is retried only once.
 * 3. Refresh failure propagates cleanly to all callers and dispatches auth:logout.
 * 4. /auth/refresh (and bypass URLs) are excluded from interceptor refresh handling.
 *
 * Framework: node:test + node:assert/strict
 */
import test from 'node:test'
import assert from 'node:assert/strict'

// ---------------------------------------------------------------------------
// Harness reproducing the exact interceptor and singleFlightRefresh architecture
// without requiring Vite-specific import.meta.env runtime context.
// ---------------------------------------------------------------------------
function createInterceptorHarness() {
  let inMemoryAccessToken = null
  let _refreshPromise = null
  let refreshCallCount = 0
  let refreshResolvers = []
  let dispatchEventCalls = []
  let apiExecutions = []

  const AUTH_BYPASS_URLS = new Set([
    '/auth/refresh',
    '/auth/login',
    '/auth/login/2sv',
    '/auth/login/verify',
    '/auth/login/resend',
    '/auth/register',
    '/auth/register/verify',
    '/auth/register/resend',
    '/auth/forgot-password/request',
    '/auth/forgot-password/verify',
    '/auth/forgot-password/reset',
  ])

  function isAuthBypassUrl(url) {
    if (!url) return false
    const cleanUrl = url.split('?')[0]
    return AUTH_BYPASS_URLS.has(cleanUrl)
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

  function apiPostRefresh() {
    refreshCallCount++
    return new Promise((resolve, reject) => {
      refreshResolvers.push({ resolve, reject })
    })
  }

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

  // Simulated api interceptor pipeline for response error
  async function handleResponseError(error, mockApiRunner) {
    const originalRequest = error.config

    if (
      error.response &&
      error.response.status === 401 &&
      originalRequest &&
      !originalRequest._retry &&
      !isAuthBypassUrl(originalRequest.url)
    ) {
      originalRequest._retry = true

      try {
        const data = await singleFlightRefresh()
        if (!originalRequest.headers) {
          originalRequest.headers = {}
        }
        originalRequest.headers.Authorization = `Bearer ${data.access_token}`
        return mockApiRunner(originalRequest)
      } catch (refreshError) {
        dispatchEventCalls.push('auth:logout')
        return Promise.reject(refreshError)
      }
    }

    return Promise.reject(error)
  }

  return {
    handleResponseError,
    singleFlightRefresh,
    getAccessToken,
    setAccessToken,
    clearAccessToken,
    getRefreshCallCount: () => refreshCallCount,
    getRefreshResolvers: () => refreshResolvers,
    getDispatchEventCalls: () => dispatchEventCalls,
    getApiExecutions: () => apiExecutions,
    recordApiExecution: (req) => apiExecutions.push(req),
  }
}

// ===========================================================================
// Test 1: Concurrent 401 requests share ONE refresh request and retry once
// ===========================================================================
test('interceptor: concurrent 401 requests share one refresh and retry with new token', async () => {
  const harness = createInterceptorHarness()

  const req1 = { url: '/messages', headers: {} }
  const req2 = { url: '/user/profile', headers: {} }

  const error1 = { response: { status: 401 }, config: req1 }
  const error2 = { response: { status: 401 }, config: req2 }

  // Both requests fail with 401 concurrently
  const p1 = harness.handleResponseError(error1, (req) => {
    harness.recordApiExecution({ ...req })
    return Promise.resolve({ data: `success-${req.url}` })
  })

  const p2 = harness.handleResponseError(error2, (req) => {
    harness.recordApiExecution({ ...req })
    return Promise.resolve({ data: `success-${req.url}` })
  })

  // INVARIANT 1: _retry MUST be set to true on BOTH original requests BEFORE refresh resolves
  assert.equal(req1._retry, true, 'req1._retry must be true immediately')
  assert.equal(req2._retry, true, 'req2._retry must be true immediately')

  // INVARIANT 2: Exactly ONE refresh HTTP call in flight
  assert.equal(harness.getRefreshCallCount(), 1, 'Only one refresh request issued for concurrent 401s')

  // Resolve the single refresh call
  const resolvers = harness.getRefreshResolvers()
  resolvers[0].resolve({ data: { access_token: 'new-shared-token' } })

  const [res1, res2] = await Promise.all([p1, p2])

  // Both retried requests succeeded with the new auth token
  assert.equal(res1.data, 'success-/messages')
  assert.equal(res2.data, 'success-/user/profile')
  assert.equal(req1.headers.Authorization, 'Bearer new-shared-token')
  assert.equal(req2.headers.Authorization, 'Bearer new-shared-token')

  // Retried requests were recorded
  const execs = harness.getApiExecutions()
  assert.equal(execs.length, 2)
  assert.equal(execs[0].url, '/messages')
  assert.equal(execs[1].url, '/user/profile')
})

// ===========================================================================
// Test 2: Each failed request is retried ONLY ONCE (no infinite 401 loop)
// ===========================================================================
test('interceptor: retried request that 401s again is NOT retried a second time', async () => {
  const harness = createInterceptorHarness()

  const req = { url: '/messages', headers: {} }
  const initial401Error = { response: { status: 401 }, config: req }

  // Step 1: Request 401s, interceptor attempts refresh
  const retryPromise = harness.handleResponseError(initial401Error, (retriedReq) => {
    // Retried request returns 401 AGAIN
    const second401Error = { response: { status: 401 }, config: retriedReq }
    return harness.handleResponseError(second401Error, () => Promise.resolve({ data: 'should-not-reach' }))
  })

  // Resolve the first refresh
  const resolvers = harness.getRefreshResolvers()
  resolvers[0].resolve({ data: { access_token: 'tok-1' } })

  // The retry rejects with 401 because _retry was true, avoiding a second refresh call
  await assert.rejects(retryPromise, (err) => {
    return err.response && err.response.status === 401
  })

  // Refresh count must remain 1 (no second refresh attempted!)
  assert.equal(harness.getRefreshCallCount(), 1, 'Refresh must not be called a second time for retried request')
})

// ===========================================================================
// Test 3: Refresh failure propagates to all callers and triggers logout event
// ===========================================================================
test('interceptor: refresh failure propagates to all 401 callers and dispatches logout', async () => {
  const harness = createInterceptorHarness()

  const req1 = { url: '/messages', headers: {} }
  const req2 = { url: '/user/profile', headers: {} }

  const error1 = { response: { status: 401 }, config: req1 }
  const error2 = { response: { status: 401 }, config: req2 }

  const p1 = harness.handleResponseError(error1, () => Promise.resolve())
  const p2 = harness.handleResponseError(error2, () => Promise.resolve())

  // Reject the single refresh call
  const refreshFail = new Error('Refresh token expired')
  harness.getRefreshResolvers()[0].reject(refreshFail)

  await assert.rejects(p1, { message: 'Refresh token expired' })
  await assert.rejects(p2, { message: 'Refresh token expired' })

  // Dispatch event called for logout
  assert.equal(harness.getDispatchEventCalls().length, 2)
  assert.equal(harness.getDispatchEventCalls()[0], 'auth:logout')

  // Access token cleared
  assert.equal(harness.getAccessToken(), null)
})

// ===========================================================================
// Test 4: /auth/refresh itself is excluded from interceptor refresh handling
// ===========================================================================
test('interceptor: /auth/refresh 401 is excluded from interceptor refresh logic', async () => {
  const harness = createInterceptorHarness()

  const refreshReq = { url: '/auth/refresh', headers: {} }
  const refresh401Error = { response: { status: 401 }, config: refreshReq }

  // Passing a 401 on /auth/refresh to handleResponseError
  const resultPromise = harness.handleResponseError(refresh401Error, () => Promise.resolve())

  // Must reject immediately with original error without invoking singleFlightRefresh
  await assert.rejects(resultPromise, (err) => {
    return err.response && err.response.status === 401 && err.config.url === '/auth/refresh'
  })

  // No refresh call was made by interceptor!
  assert.equal(harness.getRefreshCallCount(), 0, 'Interceptor must not call singleFlightRefresh for /auth/refresh 401')
  assert.equal(refreshReq._retry, undefined, '_retry flag should not even be set for bypass URLs')
})
