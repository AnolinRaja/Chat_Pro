function ChannelList({
  organization,
  channels = [],
  selectedId,
  onSelect,
  isLoading,
  error,
  onOpenCreateChannel,
  onRetry,
}) {
  return (
    <div className="flex flex-col h-full">
      {/* Organization Header */}
      <div className="border-b border-[#dbe5e1] px-3.5 sm:px-5 py-3 sm:py-4 bg-white/50">
        <div className="flex items-center justify-between gap-2 min-w-0">
          <h2 className="font-semibold text-sm sm:text-base text-[#172321] truncate">
            {organization?.organization_name || 'Organization'}
          </h2>
          <span className="shrink-0 rounded-full bg-[#e3efe9] px-2 py-0.5 text-[11px] sm:text-xs font-semibold text-[#0f766e] uppercase tracking-wider">
            {organization?.role || 'member'}
          </span>
        </div>
        <p className="mt-0.5 text-xs text-[#60736e] truncate">
          @{organization?.org_id}
        </p>
      </div>

      {/* Channels Section Header */}
      <div className="flex items-center justify-between px-3.5 sm:px-5 py-2.5 sm:py-3.5">
        <span className="text-[11px] sm:text-xs font-bold uppercase tracking-[0.16em] text-[#60736e]">
          Channels ({channels.length})
        </span>
        <button
          type="button"
          onClick={onOpenCreateChannel}
          className="flex items-center gap-1 rounded-lg bg-[#0f766e] px-2.5 py-1.5 text-xs font-semibold text-white transition hover:bg-[#0b5f59]"
        >
          <span aria-hidden="true">+</span> Add Channel
        </button>
      </div>

      {/* Channels List Area */}
      <div className="min-h-0 flex-1 overflow-y-auto px-3 space-y-1">
        {isLoading && (
          <p className="px-3 py-6 text-sm text-[#60736e]">Loading channels...</p>
        )}

        {!isLoading && error && (
          <div className="px-3 py-4 text-center">
            <p role="alert" className="text-sm text-[#a63d32] mb-2">{error}</p>
            {onRetry && (
              <button
                type="button"
                onClick={onRetry}
                className="rounded-lg border border-[#cddbd6] bg-white px-3 py-1.5 text-xs font-semibold text-[#172321] hover:bg-[#edf5f2]"
              >
                Retry
              </button>
            )}
          </div>
        )}

        {!isLoading && !error && channels.length === 0 && (
          <div className="px-3 py-8 text-center">
            <p className="text-sm text-[#60736e] mb-3">No channels found in this organization.</p>
            <button
              type="button"
              onClick={onOpenCreateChannel}
              className="rounded-lg border border-[#0f766e] bg-white px-3 py-1.5 text-xs font-semibold text-[#0f766e] hover:bg-[#d9f0eb]"
            >
              Create the first channel
            </button>
          </div>
        )}

        {!isLoading &&
          !error &&
          channels.map((channel) => {
            const isSelected = channel.id === selectedId
            return (
              <button
                key={channel.id}
                type="button"
                onClick={() => onSelect(channel)}
                className={`flex w-full items-center gap-2.5 rounded-xl px-3.5 py-2.5 text-left transition ${
                  isSelected
                    ? 'bg-[#d9f0eb] text-[#0f766e] font-semibold'
                    : 'text-[#2d413c] hover:bg-[#edf5f2]'
                }`}
              >
                <span className="text-base font-bold text-[#60736e]" aria-hidden="true">
                  #
                </span>
                <div className="min-w-0 flex-1">
                  <span className="block truncate text-sm">
                    {channel.name}
                  </span>
                  {channel.description && (
                    <span className="block truncate text-xs text-[#60736e] font-normal">
                      {channel.description}
                    </span>
                  )}
                </div>
              </button>
            )
          })}
      </div>
    </div>
  )
}

export default ChannelList
