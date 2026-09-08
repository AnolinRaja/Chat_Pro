export function ChatProSymbol({ size = 36, className = '', glow = false }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 100 100"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={`shrink-0 transition-transform ${glow ? 'drop-shadow-[0_4px_16px_rgba(0,210,190,0.45)]' : ''} ${className}`}
      aria-hidden="true"
    >
      <defs>
        {/* Canonical Fluid Mint-to-Cyan Gradient */}
        <linearGradient id="chatpro-brand-gradient" x1="75" y1="18" x2="30" y2="82" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#00f2c3" />
          <stop offset="30%" stopColor="#00dbba" />
          <stop offset="65%" stopColor="#00a3b8" />
          <stop offset="85%" stopColor="#0090c7" />
          <stop offset="100%" stopColor="#00c8fa" />
        </linearGradient>
      </defs>

      {/* Single Smooth Continuous C Shape with Rounded Terminals */}
      <path
        d="M 74 19
           C 82 19, 83 32, 74 32.5
           C 55 33.5, 37 40.5, 37 50
           C 37 59.5, 55 66.5, 74 67.5
           C 83 68, 82 81, 74 81
           C 44 81, 16 68, 16 50
           C 16 32, 44 19, 74 19 Z"
        fill="url(#chatpro-brand-gradient)"
      />

      {/* Three Centered Connection / Conversation Dots */}
      <circle cx="47" cy="50" r="4.4" fill="#008a86" />
      <circle cx="59.5" cy="50" r="4.4" fill="#00c8d1" />
      <circle cx="72" cy="50" r="4.4" fill="#5eead4" />
    </svg>
  )
}

export function ChatProLogo({ size = 36, showText = true, userName = null, className = '' }) {
  const brandTitle = userName ? `${userName}'s chatPRO` : 'chatPRO'

  return (
    <div className={`flex items-center gap-2.5 sm:gap-3 min-w-0 ${className}`}>
      <ChatProSymbol size={size} />
      {showText && (
        <span className="text-lg sm:text-xl font-bold tracking-tight text-txt-primary leading-tight font-display truncate">
          {brandTitle}
        </span>
      )}
    </div>
  )
}

export default ChatProLogo
