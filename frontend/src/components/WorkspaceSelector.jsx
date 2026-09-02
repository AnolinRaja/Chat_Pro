function getInitials(name) {
  if (!name) return 'ORG'
  const parts = name.trim().split(/\s+/)
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase()
  }
  return name.slice(0, 2).toUpperCase()
}

function WorkspaceSelector({
  memberships = [],
  activeWorkspace, // null = Direct Messages, or membership object
  onSelectWorkspace,
  onOpenJoinOrg,
}) {
  const isDMsActive = activeWorkspace === null

  return (
    <nav
      aria-label="Workspaces"
      className="flex w-16 shrink-0 flex-col items-center border-r border-[#dbe5e1] bg-[#edf3f1] py-4 gap-2.5"
    >
      {/* Direct Messages Button */}
      <button
        type="button"
        onClick={() => onSelectWorkspace(null)}
        title="Direct Messages"
        aria-label="Direct Messages"
        className={`relative grid h-11 w-11 place-items-center rounded-2xl text-xs font-bold transition-all ${
          isDMsActive
            ? 'bg-[#0f766e] text-white shadow-md shadow-[#0f766e]/20 rounded-xl'
            : 'bg-white text-[#48615c] border border-[#d2e0dc] hover:bg-[#d9f0eb] hover:text-[#0f766e] hover:rounded-xl'
        }`}
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
          <path d="M7.9 20A9 9 0 1 0 4 16.1L2 22Z" />
        </svg>
        {isDMsActive && (
          <span
            className="absolute -left-1 top-2.5 h-6 w-1 rounded-r-full bg-[#0f766e]"
            aria-hidden="true"
          />
        )}
      </button>

      {/* Separator */}
      <div className="h-px w-8 bg-[#cddbd6] my-0.5" aria-hidden="true" />

      {/* Organizations List */}
      <div className="flex flex-col items-center gap-2.5 overflow-y-auto w-full px-2 max-h-[calc(100vh-250px)]">
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
              className={`relative grid h-11 w-11 place-items-center text-xs font-bold uppercase transition-all ${
                isActive
                  ? 'bg-[#172321] text-white shadow-md rounded-xl ring-2 ring-[#0f766e]'
                  : 'bg-white text-[#2d413c] border border-[#d2e0dc] hover:bg-[#d9f0eb] hover:text-[#0f766e] hover:rounded-xl rounded-2xl'
              }`}
            >
              {initials}
              {isActive && (
                <span
                  className="absolute -left-2 top-2.5 h-6 w-1 rounded-r-full bg-[#0f766e]"
                  aria-hidden="true"
                />
              )}
            </button>
          )
        })}
      </div>

      {/* Join Organization Button */}
      <button
        type="button"
        onClick={onOpenJoinOrg}
        title="Join an Organization"
        aria-label="Join an Organization"
        className="mt-auto grid h-11 w-11 place-items-center rounded-2xl border border-dashed border-[#8eaaa5] bg-white text-[#0f766e] transition-all hover:border-[#0f766e] hover:bg-[#d9f0eb] hover:rounded-xl"
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
          <line x1="12" y1="5" x2="12" y2="19" />
          <line x1="5" y1="12" x2="19" y2="12" />
        </svg>
      </button>
    </nav>
  )
}

export default WorkspaceSelector
