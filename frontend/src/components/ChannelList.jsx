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
    <div className="flex flex-col h-full bg-glass-sidebar">
      {/* Organization Header */}
      <div className="border-b border-line-glass px-3.5 sm:px-5 py-3 sm:py-4 bg-glass-header backdrop-blur-md">
        <div className="flex items-center justify-between gap-2 min-w-0">
          <h2 className="font-semibold text-sm sm:text-base text-txt-primary truncate">
            {organization?.organization_name || 'Organization'}
          </h2>
          <span className="shrink-0 rounded-full bg-brand-soft px-2.5 py-0.5 text-[11px] sm:text-xs font-semibold text-brand uppercase tracking-wider">
            {organization?.role || 'member'}
          </span>
        </div>
        <p className="mt-0.5 text-xs text-txt-muted truncate">
          @{organization?.org_id}
        </p>
      </div>

      {/* Channels Section Header */}
      <div className="flex items-center justify-between px-3.5 sm:px-5 py-2.5 sm:py-3.5">
        <span className="text-[11px] sm:text-xs font-bold uppercase tracking-[0.16em] text-txt-muted">
          Channels ({channels.length})
        </span>
        <button
          type="button"
          onClick={onOpenCreateChannel}
          className="flex items-center gap-1 rounded-xl bg-brand px-2.5 py-1.5 text-xs font-semibold text-white transition hover:bg-brand-hover shadow-xs"
        >
          <span aria-hidden="true">+</span> Add Channel
        </button>
      </div>

      {/* Channels List Area */}
      <div className="min-h-0 flex-1 overflow-y-auto px-2 sm:px-3 space-y-1">
        {isLoading && (
          <p className="px-3 py-6 text-sm text-txt-muted">Loading channels...</p>
        )}

        {!isLoading && error && (
          <div className="px-3 py-4 text-center">
            <p role="alert" className="text-sm text-red-600 mb-2">{error}</p>
            {onRetry && (
              <button
                type="button"
                onClick={onRetry}
                className="rounded-xl border border-line-glass bg-glass-card px-3 py-1.5 text-xs font-semibold text-txt-primary hover:bg-brand-soft"
              >
                Retry
              </button>
            )}
          </div>
        )}

        {!isLoading && !error && channels.length === 0 && (
          <div className="px-3 py-8 text-center">
            <p className="text-sm text-txt-muted mb-3">No channels found in this organization.</p>
            <button
              type="button"
              onClick={onOpenCreateChannel}
              className="rounded-xl border border-brand bg-glass-card px-3 py-1.5 text-xs font-semibold text-brand hover:bg-brand-selected"
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
                    ? 'bg-brand-selected border-l-4 border-brand pl-2 sm:pl-2.5 text-brand font-semibold shadow-xs'
                    : 'text-txt-secondary hover:bg-brand-soft/60 active:bg-brand-soft'
                }`}
              >
                <span
                  className={`text-base font-bold shrink-0 ${
                    isSelected ? 'text-brand' : hasUnread ? 'text-txt-primary' : 'text-txt-muted'
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
                          ? 'font-bold text-txt-primary'
                          : isSelected
                            ? 'font-semibold text-brand'
                            : 'font-medium text-txt-primary'
                      }`}
                    >
                      {channel.name}
                    </span>
                    <span className="flex items-center gap-1.5 shrink-0">
                      {timeDisplay && (
                        <span
                          title={fullTime}
                          className={`text-[11px] sm:text-xs ${
                            hasUnread ? 'font-semibold text-brand' : 'text-txt-timestamp font-normal'
                          }`}
                        >
                          {timeDisplay}
                        </span>
                      )}
                      {hasUnread && (
                        <span
                          className="inline-flex h-4 min-w-[16px] sm:h-5 sm:min-w-[20px] items-center justify-center rounded-full bg-brand px-1 sm:px-1.5 text-[10px] sm:text-[11px] font-bold text-white shadow-xs"
                          aria-label={`${unreadCount} unread message${unreadCount > 1 ? 's' : ''}`}
                        >
                          {unreadCount > 99 ? '99+' : unreadCount}
                        </span>
                      )}
                    </span>
                  </div>
                  <span
                    className={`block truncate text-xs mt-0.5 ${
                      hasUnread ? 'font-medium text-txt-primary' : 'text-txt-muted font-normal'
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
