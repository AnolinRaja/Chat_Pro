function ConversationListItem({ conversation, isSelected, onSelect }) {
  const label = conversation.other_user?.name || 'Conversation'

  return (
    <button
      type="button"
      onClick={() => onSelect(conversation)}
      className={`flex min-h-[52px] w-full items-center gap-3 rounded-xl p-2.5 sm:p-3 text-left transition ${
        isSelected ? 'bg-[#d9f0eb]' : 'hover:bg-[#edf5f2] active:bg-[#e4ece9]'
      }`}
    >
      <span className="grid h-10 w-10 sm:h-11 sm:w-11 shrink-0 place-items-center rounded-full bg-[#172321] text-sm font-semibold text-white" aria-hidden="true">
        {label.charAt(0).toUpperCase()}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-semibold text-[#172321]">{label}</span>
        <span className="block truncate text-xs text-[#60736e]">Updated {new Date(conversation.updated_at).toLocaleString()}</span>
      </span>
    </button>
  )
}

export default ConversationListItem
