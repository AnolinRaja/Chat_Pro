import { useEffect, useState } from 'react'
import FormMessage from './FormMessage.jsx'
import { createOrgConversation } from '../services/organizationService.js'

function formatChannelError(error) {
  if (!error.response) return 'The backend is unavailable. Check that it is running and try again.'
  const detail = error.response.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map((i) => i.msg).join(' ')
  if (error.response.status === 403) return 'Access denied: only organization members can create channels.'
  if (error.response.status === 409) return 'A channel with this name already exists in this organization.'
  if (error.response.status === 422) return 'Channel name must contain only lowercase alphanumeric characters and hyphens.'
  return 'Unable to create channel.'
}

function CreateChannelModal({ isOpen, organization, onClose, onSuccess }) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    const handleKeyDown = (event) => {
      if (event.key === 'Escape') onClose()
    }
    if (isOpen) {
      document.addEventListener('keydown', handleKeyDown)
      setName('')
      setDescription('')
      setError('')
    }
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, onClose])

  if (!isOpen) return null

  const handleSubmit = async (event) => {
    event.preventDefault()
    const trimmedName = name.trim().toLowerCase()

    if (!trimmedName) {
      setError('Channel name is required.')
      return
    }

    if (!/^[a-z0-9-]+$/.test(trimmedName)) {
      setError('Channel name must contain only lowercase letters, numbers, and hyphens.')
      return
    }

    setIsSubmitting(true)
    setError('')

    try {
      const channel = await createOrgConversation(organization.organization_id, {
        name: trimmedName,
        description: description.trim(),
      })
      onSuccess(channel)
      onClose()
    } catch (err) {
      setError(formatChannelError(err))
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-[#172321]/30 p-0 sm:p-6 backdrop-blur-xs"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !isSubmitting) onClose()
      }}
    >
      <div
        className="flex max-h-[90dvh] w-full max-w-md flex-col rounded-t-2xl sm:rounded-2xl border border-[#dbe5e1] bg-white shadow-2xl overflow-hidden"
        role="dialog"
        aria-modal="true"
        aria-labelledby="create-channel-title"
      >
        <div className="flex shrink-0 items-start justify-between gap-3 border-b border-[#edf2f0] p-4 sm:p-6">
          <div className="min-w-0">
            <p className="text-[11px] sm:text-xs font-semibold uppercase tracking-[0.16em] text-[#0f766e] truncate">
              {organization?.organization_name || 'Organization'}
            </p>
            <h2 id="create-channel-title" className="mt-1 text-xl sm:text-2xl font-semibold text-[#172321]">
              Create a Channel
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={isSubmitting}
            aria-label="Close create channel dialog"
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-lg text-[#60736e] hover:bg-[#edf5f2]"
          >
            ✕
          </button>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-1 flex-col overflow-hidden">
          <div className="flex-1 min-h-0 overflow-y-auto p-4 sm:p-6 space-y-4">
            <FormMessage>{error}</FormMessage>

            <div>
              <label htmlFor="channel-name" className="block text-sm font-medium text-[#172321]">
                Channel Name
              </label>
              <div className="relative mt-1.5 flex items-center">
                <span className="absolute left-3.5 text-base font-bold text-[#60736e]">#</span>
                <input
                  id="channel-name"
                  type="text"
                  required
                  autoFocus
                  value={name}
                  onChange={(e) => setName(e.target.value.toLowerCase().replace(/\s+/g, '-'))}
                  placeholder="e.g. general, announcements"
                  disabled={isSubmitting}
                  className="w-full rounded-xl border border-[#cddbd6] pl-8 pr-4 py-2.5 text-base sm:text-sm outline-none focus:border-[#0f766e] focus:ring-2 focus:ring-[#99d6cc] disabled:bg-[#f4f7f6]"
                />
              </div>
              <p className="mt-1 text-xs text-[#60736e]">
                Use lowercase letters, numbers, and hyphens.
              </p>
            </div>

            <div>
              <label htmlFor="channel-description" className="block text-sm font-medium text-[#172321]">
                Description <span className="text-xs text-[#60736e] font-normal">(optional)</span>
              </label>
              <textarea
                id="channel-description"
                rows="3"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="What is this channel about?"
                disabled={isSubmitting}
                className="mt-1.5 w-full rounded-xl border border-[#cddbd6] px-4 py-2.5 text-base sm:text-sm outline-none focus:border-[#0f766e] focus:ring-2 focus:ring-[#99d6cc] disabled:bg-[#f4f7f6] resize-none"
              />
            </div>
          </div>

          <div className="flex flex-col-reverse sm:flex-row items-stretch sm:items-center justify-end gap-2 sm:gap-3 border-t border-[#edf2f0] p-4 sm:p-6 bg-white shrink-0">
            <button
              type="button"
              onClick={onClose}
              disabled={isSubmitting}
              className="flex min-h-[44px] items-center justify-center rounded-lg px-4 py-2.5 text-sm font-semibold text-[#60736e] hover:bg-[#edf5f2] disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="flex min-h-[44px] items-center justify-center rounded-lg bg-[#0f766e] px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-[#0b5f59] disabled:opacity-50"
            >
              {isSubmitting ? 'Creating...' : 'Create Channel'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default CreateChannelModal
