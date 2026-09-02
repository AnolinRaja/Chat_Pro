import { useEffect, useState } from 'react'
import FormMessage from './FormMessage.jsx'
import { joinOrganization } from '../services/organizationService.js'

function formatJoinError(error) {
  if (!error.response) return 'The backend is unavailable. Check that it is running and try again.'
  const detail = error.response.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map((i) => i.msg).join(' ')
  if (error.response.status === 400) return 'Invalid organization ID or join code.'
  if (error.response.status === 404) return 'Organization not found.'
  if (error.response.status === 409) return 'You are already a member of this organization.'
  if (error.response.status === 429) return 'Too many join requests. Please wait and try again.'
  return 'Unable to join organization.'
}

function JoinOrgModal({ isOpen, onClose, onSuccess }) {
  const [orgId, setOrgId] = useState('')
  const [joinCode, setJoinCode] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [successInfo, setSuccessInfo] = useState(null)

  useEffect(() => {
    const handleKeyDown = (event) => {
      if (event.key === 'Escape') onClose()
    }
    if (isOpen) {
      document.addEventListener('keydown', handleKeyDown)
    }
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, onClose])

  if (!isOpen) return null

  const handleSubmit = async (event) => {
    event.preventDefault()
    const trimmedOrgId = orgId.trim().toLowerCase()
    const trimmedCode = joinCode.trim()

    if (!trimmedOrgId) {
      setError('Organization ID is required.')
      return
    }
    if (!trimmedCode) {
      setError('Join code is required.')
      return
    }

    setIsSubmitting(true)
    setError('')
    setSuccessInfo(null)

    try {
      const result = await joinOrganization({
        orgId: trimmedOrgId,
        joinCode: trimmedCode,
      })

      setSuccessInfo(
        result.status === 'approved'
          ? 'Successfully joined the organization!'
          : 'Join request submitted! An administrator will review your request.'
      )

      setTimeout(() => {
        onSuccess(result)
        onClose()
      }, 1200)
    } catch (err) {
      setError(formatJoinError(err))
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-[#172321]/30 p-0 sm:items-center sm:p-6"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !isSubmitting) onClose()
      }}
    >
      <div
        className="w-full max-w-md rounded-t-2xl bg-white p-6 shadow-2xl sm:rounded-2xl border border-[#dbe5e1]"
        role="dialog"
        aria-modal="true"
        aria-labelledby="join-org-title"
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#0f766e]">
              Workspace
            </p>
            <h2 id="join-org-title" className="mt-1 text-2xl font-semibold text-[#172321]">
              Join Organization
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={isSubmitting}
            aria-label="Close join organization dialog"
            className="rounded-lg px-3 py-1.5 text-xl leading-none text-[#60736e] hover:bg-[#edf5f2]"
          >
            x
          </button>
        </div>

        <form onSubmit={handleSubmit} className="mt-5 space-y-4">
          <FormMessage>{error}</FormMessage>

          {successInfo && (
            <p role="status" className="rounded-xl bg-[#d9f0eb] p-3 text-sm font-semibold text-[#0f766e]">
              {successInfo}
            </p>
          )}

          <div>
            <label htmlFor="join-org-id" className="block text-sm font-medium text-[#172321]">
              Organization ID
            </label>
            <input
              id="join-org-id"
              type="text"
              required
              autoFocus
              value={orgId}
              onChange={(e) => setOrgId(e.target.value)}
              placeholder="e.g. acme-corp or dev-org"
              disabled={isSubmitting}
              className="mt-1.5 w-full rounded-xl border border-[#cddbd6] px-4 py-2.5 text-sm outline-none focus:border-[#0f766e] focus:ring-2 focus:ring-[#99d6cc] disabled:bg-[#f4f7f6]"
            />
          </div>

          <div>
            <label htmlFor="join-org-code" className="block text-sm font-medium text-[#172321]">
              Join Code
            </label>
            <input
              id="join-org-code"
              type="password"
              required
              value={joinCode}
              onChange={(e) => setJoinCode(e.target.value)}
              placeholder="Enter the secret join code"
              disabled={isSubmitting}
              className="mt-1.5 w-full rounded-xl border border-[#cddbd6] px-4 py-2.5 text-sm outline-none focus:border-[#0f766e] focus:ring-2 focus:ring-[#99d6cc] disabled:bg-[#f4f7f6]"
            />
            <p className="mt-1 text-xs text-[#60736e]">
              Obtain the join code from your organization administrator.
            </p>
          </div>

          <div className="flex items-center justify-end gap-3 pt-3">
            <button
              type="button"
              onClick={onClose}
              disabled={isSubmitting}
              className="rounded-lg px-4 py-2.5 text-sm font-semibold text-[#60736e] hover:bg-[#edf5f2] disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="rounded-lg bg-[#0f766e] px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-[#0b5f59] disabled:opacity-50"
            >
              {isSubmitting ? 'Joining...' : 'Join Organization'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default JoinOrgModal
