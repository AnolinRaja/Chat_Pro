function ConversationListItem({ conversation, isSelected, onSelect }) {
  const label = conversation.other_user?.name || 'Conversation'

  return (
    <button type="button" onClick={() => onSelect(conversation)} className={`flex w-full items-center gap-3 rounded-xl p-3 text-left transition ${isSelected ? 'bg-[#d9f0eb]' : 'hover:bg-[#edf5f2]'}`}>
      <span className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-[#172321] text-sm font-semibold text-white" aria-hidden="true">{label.charAt(0).toUpperCase()}</span>
      <span className="min-w-0">
        <span className="block truncate text-sm font-semibold text-[#172321]">{label}</span>
        <span className="block truncate text-xs text-[#60736e]">Updated {new Date(conversation.updated_at).toLocaleString()}</span>
      </span>
    </button>
  )
}

export default ConversationListItem
