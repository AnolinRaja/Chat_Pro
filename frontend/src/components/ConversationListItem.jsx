import { formatFullTimestamp, formatRelativeTime } from '../utils/dateUtils.js'

function getAvatarColor(name) {
  const colors = [
    'bg-teal-600/90 text-white',
    'bg-sky-600/90 text-white',
    'bg-rose-500/90 text-white',
    'bg-amber-600/90 text-white',
    'bg-indigo-600/90 text-white',
    'bg-emerald-600/90 text-white',
    'bg-cyan-700/90 text-white',
  ]
  if (!name) return colors[0]
  let hash = 0
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash)
  }
  return colors[Math.abs(hash) % colors.length]
}

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
  const avatarClass = getAvatarColor(label)

  return (
    <button
      type="button"
      onClick={() => onSelect(conversation)}
      className={`group relative flex min-h-[64px] w-full items-center gap-3 rounded-2xl p-3 text-left transition-all duration-150 ${
        isSelected
          ? 'bg-gradient-to-r from-teal-500/25 to-emerald-500/20 shadow-[0_4px_24px_rgba(0,40,35,0.25)] border border-teal-300/40 text-txt-primary backdrop-blur-md'
          : 'border border-white/20 bg-white/30 hover:border-white/50 hover:bg-white/55 hover:shadow-xs active:scale-[0.99] backdrop-blur-xs'
      }`}
    >
      <div className="relative shrink-0">
        <span
          className={`grid h-11 w-11 place-items-center rounded-2xl text-sm font-bold shadow-xs transition-colors ${
            isSelected
              ? 'bg-white text-teal-800 shadow-sm font-black'
              : hasUnread
                ? 'bg-txt-primary text-white ring-2 ring-brand/40'
                : avatarClass
          }`}
          aria-hidden="true"
        >
          {label.charAt(0).toUpperCase()}
        </span>
        {hasUnread && (
          <span className="absolute -top-1 -right-1 h-3.5 w-3.5 rounded-full bg-teal-400 ring-2 ring-white" />
        )}
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-1.5">
          <span
            className={`truncate text-sm tracking-tight ${
              hasUnread ? 'font-bold text-txt-primary' : isSelected ? 'font-bold text-txt-primary' : 'font-semibold text-txt-primary'
            }`}
          >
            {label}
          </span>
          <div className="flex items-center gap-1.5 shrink-0">
            {timeDisplay && (
              <span
                title={fullTime}
                className={`text-[11px] font-medium font-mono ${
                  hasUnread ? 'font-bold text-teal-700' : 'text-txt-timestamp'
                }`}
              >
                {timeDisplay}
              </span>
            )}
            {hasUnread && (
              <span
                className="inline-flex h-5 min-w-[20px] items-center justify-center rounded-full bg-teal-500 px-1.5 text-[11px] font-bold text-white shadow-xs"
                aria-label={`${unreadCount} unread message${unreadCount > 1 ? 's' : ''}`}
              >
                {unreadCount > 99 ? '99+' : unreadCount}
              </span>
            )}
          </div>
        </div>
        <p
          className={`truncate text-xs mt-0.5 leading-relaxed ${
            hasUnread
              ? 'font-semibold text-txt-primary'
              : isSelected
                ? 'text-txt-secondary font-medium'
                : 'text-txt-muted'
          }`}
        >
          {previewText}
        </p>
      </div>
    </button>
  )
}

export default ConversationListItem
