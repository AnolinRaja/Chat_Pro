import { useEffect } from 'react'

function formatDate(isoString) {
  if (!isoString) return ''
  try {
    const d = new Date(isoString)
    return d.toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return isoString
  }
}

function StatusBadge({ status }) {
  if (status === 'PENDING') {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-300 bg-amber-50 px-2.5 py-0.5 text-xs font-semibold text-amber-800">
        <span className="h-1.5 w-1.5 rounded-full bg-amber-500 animate-pulse" aria-hidden="true" />
        Pending
      </span>
    )
  }

  if (status === 'APPROVED') {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-300 bg-emerald-50 px-2.5 py-0.5 text-xs font-semibold text-emerald-800">
        <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" aria-hidden="true" />
        Approved
      </span>
    )
  }

  if (status === 'REJECTED') {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-rose-300 bg-rose-50 px-2.5 py-0.5 text-xs font-semibold text-rose-800">
        <span className="h-1.5 w-1.5 rounded-full bg-rose-500" aria-hidden="true" />
        Rejected
      </span>
    )
  }

  return (
    <span className="inline-flex items-center rounded-full border border-gray-300 bg-gray-50 px-2.5 py-0.5 text-xs font-semibold text-gray-700">
      {status}
    </span>
  )
}

function OrgRequestsModal({
  isOpen,
  requests = [],
  memberships = [],
  isLoading = false,
  error = '',
  onClose,
  onRefresh,
  onOpenJoinOrg,
  onSelectWorkspace,
}) {
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

  const pendingCount = requests.filter((r) => r.status === 'PENDING').length

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-[#172321]/30 p-0 sm:items-center sm:p-6"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose()
      }}
    >
      <div
        className="flex max-h-[85vh] w-full max-w-lg flex-col rounded-t-2xl bg-white shadow-2xl sm:rounded-2xl border border-[#dbe5e1] overflow-hidden"
        role="dialog"
        aria-modal="true"
        aria-labelledby="org-requests-title"
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-[#dbe5e1] px-6 py-4">
          <div className="flex items-center gap-2.5">
            <div>
              <div className="flex items-center gap-2">
                <h2 id="org-requests-title" className="text-lg font-semibold text-[#172321]">
                  Organization Requests
                </h2>
                {pendingCount > 0 && (
                  <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-800">
                    {pendingCount} pending
                  </span>
                )}
              </div>
              <p className="text-xs text-[#60736e]">
                Status of your organization membership requests
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onRefresh}
              disabled={isLoading}
              title="Refresh requests"
              aria-label="Refresh requests"
              className="inline-flex items-center gap-1.5 rounded-lg border border-[#d2e0dc] bg-white px-2.5 py-1.5 text-xs font-medium text-[#48615c] transition hover:bg-[#edf5f2] disabled:opacity-50"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                className={`h-3.5 w-3.5 ${isLoading ? 'animate-spin' : ''}`}
                aria-hidden="true"
              >
                <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
                <path d="M3 3v5h5" />
                <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16" />
                <path d="M16 21h5v-5" />
              </svg>
              <span>{isLoading ? 'Refreshing...' : 'Refresh'}</span>
            </button>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close organization requests dialog"
              className="rounded-lg px-2.5 py-1 text-xl leading-none text-[#60736e] hover:bg-[#edf5f2]"
            >
              x
            </button>
          </div>
        </div>

        {/* Body Content */}
        <div className="min-h-0 flex-1 overflow-y-auto p-6 space-y-3">
          {error && (
            <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">
              <p className="font-semibold">Unable to load requests</p>
              <p className="text-xs mt-0.5">{error}</p>
            </div>
          )}

          {requests.length === 0 ? (
            <div className="py-10 text-center">
              <div className="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-[#edf5f2] text-xl text-[#0f766e]">
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  className="h-6 w-6"
                  aria-hidden="true"
                >
                  <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
                  <path d="M13.73 21a2 2 0 0 1-3.46 0" />
                </svg>
              </div>
              <h3 className="mt-3 text-base font-semibold text-[#172321]">
                No organization requests
              </h3>
              <p className="mt-1 text-xs text-[#60736e]">
                You have not submitted any join requests yet.
              </p>
              {onOpenJoinOrg && (
                <button
                  type="button"
                  onClick={onOpenJoinOrg}
                  className="mt-4 inline-flex items-center gap-1.5 rounded-lg bg-[#0f766e] px-4 py-2 text-xs font-semibold text-white transition hover:bg-[#0b5f59]"
                >
                  + Join an Organization
                </button>
              )}
            </div>
          ) : (
            requests.map((req) => {
              const isApproved = req.status === 'APPROVED'
              const isPending = req.status === 'PENDING'
              const isRejected = req.status === 'REJECTED'

              const matchingMembership = isApproved
                ? memberships.find((m) => m.organization_id === req.organization_id)
                : null

              return (
                <div
                  key={req.id}
                  className="rounded-xl border border-[#dbe5e1] bg-[#fbfcfc] p-4 transition-all hover:border-[#b8cfc8] hover:bg-white"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <h4 className="font-semibold text-sm text-[#172321] truncate">
                          {req.organization_name || 'Organization'}
                        </h4>
                        {req.org_id && (
                          <span className="text-xs text-[#60736e]">
                            @{req.org_id}
                          </span>
                        )}
                      </div>

                      {/* Status explanation */}
                      <p className="mt-1 text-xs text-[#48615c]">
                        {isPending && 'Waiting for administrator approval'}
                        {isApproved && 'You are now a member'}
                        {isRejected && 'Your request was rejected'}
                      </p>
                    </div>

                    <div className="shrink-0 flex flex-col items-end gap-2">
                      <StatusBadge status={req.status} />

                      {isApproved && matchingMembership && onSelectWorkspace && (
                        <button
                          type="button"
                          onClick={() => onSelectWorkspace(req.organization_id)}
                          className="rounded-md bg-[#0f766e] px-2.5 py-1 text-xs font-semibold text-white hover:bg-[#0b5f59]"
                        >
                          Open Workspace
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Dates footer */}
                  <div className="mt-3 flex items-center justify-between border-t border-[#edf2f0] pt-2 text-[11px] text-[#60736e]">
                    <span>Requested: {formatDate(req.created_at)}</span>
                    {req.updated_at && req.updated_at !== req.created_at && (
                      <span>Updated: {formatDate(req.updated_at)}</span>
                    )}
                  </div>
                </div>
              )
            })
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-[#dbe5e1] bg-[#fbfcfc] px-6 py-3">
          <span className="text-xs text-[#60736e]">
            {requests.length} request{requests.length === 1 ? '' : 's'} total
          </span>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg px-4 py-1.5 text-xs font-semibold text-[#60736e] hover:bg-[#edf5f2]"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  )
}

export default OrgRequestsModal
