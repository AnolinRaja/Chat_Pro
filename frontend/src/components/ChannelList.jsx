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
    <div className="flex flex-col h-full bg-transparent">
      {/* Organization Header */}
      <div className="border-b border-white/30 px-3.5 sm:px-5 py-3 sm:py-4 bg-white/20 backdrop-blur-sm">
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
          className="flex items-center gap-1 rounded-xl bg-gradient-to-r from-[#0f766e] to-[#0c635c] px-2.5 py-1.5 text-xs font-semibold text-white transition hover:brightness-110 shadow-xs"
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
                className="rounded-xl border border-white/40 bg-white/45 px-3 py-1.5 text-xs font-semibold text-txt-primary hover:bg-white/75"
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
              className="rounded-xl border border-brand bg-white/45 px-3 py-1.5 text-xs font-semibold text-brand hover:bg-brand-selected"
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
                className={`group relative flex min-h-[56px] w-full items-center gap-2.5 rounded-2xl px-3.5 py-2.5 text-left transition-all duration-150 ${
                  isSelected
                    ? 'bg-white/80 shadow-[0_4px_20px_-4px_rgba(0,30,25,0.20)] border border-brand/40 text-txt-primary backdrop-blur-md'
                    : 'border border-white/20 bg-white/30 hover:border-white/60 hover:bg-white/60 hover:shadow-xs active:scale-[0.99] backdrop-blur-xs'
                }`}
              >
                {isSelected && (
                  <span className="absolute left-0 top-2.5 bottom-2.5 w-1 rounded-r-full bg-brand" aria-hidden="true" />
                )}
                <span
                  className={`grid h-8 w-8 place-items-center rounded-xl text-base font-bold shrink-0 transition-colors ${
                    isSelected
                      ? 'bg-brand text-white shadow-xs'
                      : hasUnread
                        ? 'bg-txt-primary text-white'
                        : 'bg-brand-soft text-brand'
                  }`}
                  aria-hidden="true"
                >
                  #
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-1.5">
                    <span
                      className={`truncate text-sm tracking-tight ${
                        hasUnread
                          ? 'font-bold text-txt-primary'
                          : isSelected
                            ? 'font-bold text-txt-primary'
                            : 'font-semibold text-txt-primary'
                      }`}
                    >
                      {channel.name}
                    </span>
                    <div className="flex items-center gap-1.5 shrink-0">
                      {timeDisplay && (
                        <span
                          title={fullTime}
                          className={`text-[11px] font-medium font-mono ${
                            hasUnread ? 'font-bold text-brand' : 'text-txt-timestamp'
                          }`}
                        >
                          {timeDisplay}
                        </span>
                      )}
                      {hasUnread && (
                        <span
                          className="inline-flex h-5 min-w-[20px] items-center justify-center rounded-full bg-brand px-1.5 text-[11px] font-bold text-white shadow-xs"
                          aria-label={`${unreadCount} unread message${unreadCount > 1 ? 's' : ''}`}
                        >
                          {unreadCount > 99 ? '99+' : unreadCount}
                        </span>
                      )}
                    </div>
                  </div>
                  <p
                    className={`truncate text-xs mt-0.5 leading-relaxed ${
                      hasUnread ? 'font-semibold text-txt-primary' : 'text-txt-muted'
                    }`}
                  >
                    {previewText}
                  </p>
                </div>
              </button>
            )
          })}
      </div>
    </div>
  )
}

export default ChannelList
