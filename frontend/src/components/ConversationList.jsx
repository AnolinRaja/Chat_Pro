import ConversationListItem from './ConversationListItem.jsx'

function ConversationList({
  conversations = [],
  selectedId,
  onSelect,
  isLoading,
  error,
  activityState = {},
}) {
  if (isLoading) return <p className="px-5 py-8 text-sm text-[#60736e]">Loading conversations...</p>
  if (error) return <p role="alert" className="px-5 py-8 text-sm text-[#a63d32]">{error}</p>
  if (!conversations.length) return <p className="px-5 py-8 text-sm leading-6 text-[#60736e]">No conversations yet. Start one with a teammate above.</p>

  return (
    <div className="space-y-1 px-2 sm:px-3">
      {conversations.map((conversation) => {
        const activity = activityState[conversation.id] || {}
        return (
          <ConversationListItem
            key={conversation.id}
            conversation={conversation}
            isSelected={conversation.id === selectedId}
            onSelect={onSelect}
            preview={activity.latestPreview}
            timestamp={activity.latestMessageAt || conversation.updated_at}
            unreadCount={activity.unreadCount || 0}
          />
        )
      })}
    </div>
  )
}

export default ConversationList
