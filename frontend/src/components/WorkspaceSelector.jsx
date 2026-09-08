import { ChatProSymbol } from './ChatProLogo.jsx'

function getInitials(name) {
  if (!name) return 'U'
  const parts = name.trim().split(/\s+/)
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase()
  }
  return name.slice(0, 2).toUpperCase()
}

function WorkspaceSelector({
  memberships = [],
  requests = [],
  activeWorkspace, // null = Direct Messages, or membership object
  onSelectWorkspace,
  onOpenJoinOrg,
  onOpenRequestsModal,
  user,
  className = '',
}) {
  const isDMsActive = activeWorkspace === null
  const pendingCount = requests.filter((r) => r.status === 'PENDING').length
  const userInitial = user?.name ? user.name.charAt(0).toUpperCase() : 'U'

  return (
    <nav
      aria-label="Workspaces"
      className={`flex w-14 sm:w-16 shrink-0 flex-col items-center border-r border-white/30 bg-white/20 backdrop-blur-xl py-3 sm:py-4 gap-2.5 sm:gap-3 ${className}`}
    >
      {/* Brand Logo Symbol at Top of Rail */}
      <div className="grid h-10 w-10 sm:h-11 sm:w-11 place-items-center rounded-2xl bg-white/50 p-1.5 backdrop-blur-md border border-white/60 shadow-sm" title="ChatPRO">
        <ChatProSymbol size={26} glow />
      </div>

      <div className="h-px w-6 sm:w-8 bg-white/30 my-0.5" aria-hidden="true" />

      {/* Direct Messages Icon Button */}
      <button
        type="button"
        onClick={() => onSelectWorkspace(null)}
        title="Direct Messages"
        aria-label="Direct Messages"
        className={`relative grid h-10 w-10 sm:h-11 sm:w-11 place-items-center rounded-2xl text-xs font-bold transition-all ${
          isDMsActive
            ? 'bg-gradient-to-br from-teal-500 to-emerald-600 text-white shadow-md shadow-brand/30 rounded-xl ring-2 ring-white/60'
            : 'bg-white/40 text-txt-secondary border border-white/40 hover:bg-white/70 hover:text-brand hover:rounded-xl shadow-xs backdrop-blur-sm'
        }`}
      >
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
        </svg>
        {isDMsActive && (
          <span
            className="absolute -left-1 top-2.5 h-5 sm:h-6 w-1 rounded-r-full bg-white"
            aria-hidden="true"
          />
        )}
      </button>

      {/* Organization / Team Memberships List */}
      <div className="flex flex-col items-center gap-2 sm:gap-2.5 overflow-y-auto w-full px-1.5 sm:px-2 max-h-[calc(100vh-280px)]">
        {memberships.map((membership) => {
          const isActive = activeWorkspace?.organization_id === membership.organization_id
          const initials = getInitials(membership.organization_name)

          return (
            <button
              key={membership.id || membership.organization_id}
              type="button"
              onClick={() => onSelectWorkspace(membership)}
              title={`${membership.organization_name} (@${membership.org_id})`}
              aria-label={`${membership.organization_name} workspace`}
              className={`relative grid h-10 w-10 sm:h-11 sm:w-11 place-items-center text-xs font-bold uppercase transition-all ${
                isActive
                  ? 'bg-txt-primary text-white shadow-md rounded-xl ring-2 ring-brand'
                  : 'bg-white/40 text-txt-secondary border border-white/40 hover:bg-white/70 hover:text-brand hover:rounded-xl rounded-2xl shadow-xs backdrop-blur-sm'
              }`}
            >
              {initials}
              {isActive && (
                <span
                  className="absolute -left-1 sm:-left-2 top-2.5 h-5 sm:h-6 w-1 rounded-r-full bg-brand"
                  aria-hidden="true"
                />
              )}
            </button>
          )
        })}

        {/* Join / Create Organization Button */}
        <button
          type="button"
          onClick={onOpenJoinOrg}
          title="Join or Create Organization"
          aria-label="Join or Create Organization"
          className="grid h-10 w-10 sm:h-11 sm:w-11 place-items-center rounded-2xl border border-dashed border-teal-600/50 bg-white/40 text-teal-700 transition-all hover:border-teal-700 hover:bg-white/70 hover:rounded-xl shadow-xs backdrop-blur-sm"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="h-5 w-5"
            aria-hidden="true"
          >
            <circle cx="12" cy="12" r="9" />
            <line x1="12" y1="8" x2="12" y2="16" />
            <line x1="8" y1="12" x2="16" y2="12" />
          </svg>
        </button>
      </div>

      {/* Bottom Section: Requests + User Profile Avatar */}
      <div className="mt-auto flex flex-col items-center gap-2 sm:gap-2.5">
        {/* Organization Requests Button */}
        <button
          type="button"
          onClick={onOpenRequestsModal}
          title={
            pendingCount > 0
              ? `Organization Requests (${pendingCount} pending)`
              : 'Organization Requests'
          }
          aria-label={
            pendingCount > 0
              ? `Organization Requests (${pendingCount} pending)`
              : 'Organization Requests'
          }
          className="relative grid h-10 w-10 sm:h-11 sm:w-11 place-items-center rounded-2xl border border-white/40 bg-white/40 text-txt-secondary transition-all hover:bg-white/70 hover:text-brand hover:rounded-xl shadow-xs backdrop-blur-sm"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="h-5 w-5"
            aria-hidden="true"
          >
            <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
            <path d="M13.73 21a2 2 0 0 1-3.46 0" />
          </svg>

          {pendingCount > 0 && (
            <span
              className="absolute -top-1.5 -right-1.5 flex h-4.5 min-w-4.5 sm:h-5 sm:min-w-5 items-center justify-center rounded-full bg-amber-500 px-1 text-[9px] sm:text-[10px] font-bold text-white shadow-xs ring-2 ring-white"
              aria-label={`${pendingCount} pending requests`}
            >
              {pendingCount}
            </span>
          )}
        </button>

        {/* User Profile Avatar */}
        <div
          title={user?.name ? `${user.name} (${user.email || ''})` : 'User Profile'}
          className="grid h-10 w-10 sm:h-11 sm:w-11 place-items-center rounded-2xl bg-gradient-to-tr from-teal-700 to-emerald-600 font-bold text-white shadow-sm border border-white/60 text-sm"
        >
          {userInitial}
        </div>
      </div>
    </nav>
  )
}

export default WorkspaceSelector
