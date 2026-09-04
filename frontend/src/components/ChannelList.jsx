import { formatFullTimestamp, formatRelativeTime } from '../utils/dateUtils.js'

function ChannelList({
  organization,
  channels = [],
  selectedId,
  onSelect,
  isLoading,
  error,
  onOpenCreateChannel,
  onRetry,
  activityState = {},
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
      <div className="min-h-0 flex-1 overflow-y-auto px-2 sm:px-3 space-y-1">
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
            const activity = activityState[channel.id] || {}
            const unreadCount = activity.unreadCount || 0
            const hasUnread = unreadCount > 0
            const timestamp = activity.latestMessageAt || channel.updated_at
            const timeDisplay = formatRelativeTime(timestamp)
            const fullTime = formatFullTimestamp(timestamp)
            const previewText = activity.latestPreview || channel.description || 'No messages yet'

            return (
              <button
                key={channel.id}
                type="button"
                onClick={() => onSelect(channel)}
                className={`group flex min-h-[52px] w-full items-center gap-2.5 rounded-xl px-3 py-2 sm:px-3.5 sm:py-2.5 text-left transition ${
                  isSelected
                    ? 'bg-[#d9f0eb] border-l-4 border-[#0f766e] pl-2 sm:pl-2.5 text-[#0f766e] font-semibold shadow-xs'
                    : 'text-[#2d413c] hover:bg-[#edf5f2] active:bg-[#e4ece9]'
                }`}
              >
                <span
                  className={`text-base font-bold shrink-0 ${
                    isSelected ? 'text-[#0f766e]' : hasUnread ? 'text-[#172321]' : 'text-[#60736e]'
                  }`}
                  aria-hidden="true"
                >
                  #
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-1.5">
                    <span
                      className={`truncate text-sm ${
                        hasUnread
                          ? 'font-bold text-[#172321]'
                          : isSelected
                            ? 'font-semibold text-[#0f766e]'
                            : 'font-medium text-[#172321]'
                      }`}
                    >
                      {channel.name}
                    </span>
                    <span className="flex items-center gap-1.5 shrink-0">
                      {timeDisplay && (
                        <span
                          title={fullTime}
                          className={`text-[11px] sm:text-xs ${
                            hasUnread ? 'font-semibold text-[#0f766e]' : 'text-[#60736e] font-normal'
                          }`}
                        >
                          {timeDisplay}
                        </span>
                      )}
                      {hasUnread && (
                        <span
                          className="inline-flex h-4 min-w-[16px] sm:h-5 sm:min-w-[20px] items-center justify-center rounded-full bg-[#0f766e] px-1 sm:px-1.5 text-[10px] sm:text-[11px] font-bold text-white shadow-xs"
                          aria-label={`${unreadCount} unread message${unreadCount > 1 ? 's' : ''}`}
                        >
                          {unreadCount > 99 ? '99+' : unreadCount}
                        </span>
                      )}
                    </span>
                  </div>
                  <span
                    className={`block truncate text-xs mt-0.5 ${
                      hasUnread ? 'font-medium text-[#172321]' : 'text-[#60736e] font-normal'
                    }`}
                  >
                    {previewText}
                  </span>
                </div>
              </button>
            )
          })}
      </div>
    </div>
  )
}

export default ChannelList
