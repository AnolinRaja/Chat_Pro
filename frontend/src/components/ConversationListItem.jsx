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
          ? 'bg-[#d9f0eb] border-l-4 border-[#0f766e] pl-2 sm:pl-2.5 shadow-xs'
          : 'hover:bg-[#edf5f2] active:bg-[#e4ece9]'
      }`}
    >
      <span
        className={`grid h-10 w-10 sm:h-11 sm:w-11 shrink-0 place-items-center rounded-full text-sm font-semibold transition ${
          isSelected
            ? 'bg-[#0f766e] text-white'
            : hasUnread
              ? 'bg-[#172321] text-white ring-2 ring-[#0f766e]'
              : 'bg-[#172321] text-white'
        }`}
        aria-hidden="true"
      >
        {label.charAt(0).toUpperCase()}
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-center justify-between gap-1.5">
          <span
            className={`truncate text-sm ${
              hasUnread ? 'font-bold text-[#172321]' : isSelected ? 'font-semibold text-[#0f766e]' : 'font-semibold text-[#172321]'
            }`}
          >
            {label}
          </span>
          <span className="flex items-center gap-1.5 shrink-0">
            {timeDisplay && (
              <span
                title={fullTime}
                className={`text-[11px] sm:text-xs ${
                  hasUnread ? 'font-semibold text-[#0f766e]' : 'text-[#60736e]'
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
        </span>
        <span
          className={`block truncate text-xs mt-0.5 ${
            hasUnread
              ? 'font-medium text-[#172321]'
              : 'text-[#60736e]'
          }`}
        >
          {previewText}
        </span>
      </span>
    </button>
  )
}

export default ConversationListItem
