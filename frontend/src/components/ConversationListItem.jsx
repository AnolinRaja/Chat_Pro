import { formatFullTimestamp, formatRelativeTime } from '../utils/dateUtils.js'

function ConversationListItem({
  conversation,
  isSelected,
  onSelect,
  preview = '',
  timestamp = null,
  unreadCount = 0,
}) {
  const label = conversation.other_user?.name || 'Conversation'
  const timeDisplay = formatRelativeTime(timestamp || conversation.updated_at)
  const fullTime = formatFullTimestamp(timestamp || conversation.updated_at)
  const hasUnread = unreadCount > 0
  const previewText = preview || 'No messages yet'

  return (
    <button
      type="button"
      onClick={() => onSelect(conversation)}
      className={`group flex min-h-[58px] w-full items-center gap-3 rounded-xl p-2.5 sm:p-3 text-left transition ${
        isSelected
          ? 'bg-brand-selected border-l-4 border-brand pl-2 sm:pl-2.5 shadow-xs'
          : 'hover:bg-brand-soft/60 active:bg-brand-soft'
      }`}
    >
      <span
        className={`grid h-10 w-10 sm:h-11 sm:w-11 shrink-0 place-items-center rounded-full text-sm font-semibold transition ${
          isSelected
            ? 'bg-brand text-white'
            : hasUnread
              ? 'bg-txt-primary text-white ring-2 ring-brand'
              : 'bg-txt-primary text-white'
        }`}
        aria-hidden="true"
      >
        {label.charAt(0).toUpperCase()}
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-center justify-between gap-1.5">
          <span
            className={`truncate text-sm ${
              hasUnread ? 'font-bold text-txt-primary' : isSelected ? 'font-semibold text-brand' : 'font-semibold text-txt-primary'
            }`}
          >
            {label}
          </span>
          <span className="flex items-center gap-1.5 shrink-0">
            {timeDisplay && (
              <span
                title={fullTime}
                className={`text-[11px] sm:text-xs ${
                  hasUnread ? 'font-semibold text-brand' : 'text-txt-timestamp'
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
        </span>
        <span
          className={`block truncate text-xs mt-0.5 ${
            hasUnread
              ? 'font-medium text-txt-primary'
              : 'text-txt-muted'
          }`}
        >
          {previewText}
        </span>
      </span>
    </button>
  )
}

export default ConversationListItem
