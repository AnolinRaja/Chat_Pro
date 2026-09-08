import { ChatProSymbol } from './ChatProLogo.jsx'

function AuthCard({ eyebrow, title, description, children, footer, showLogo = true }) {
  return (
    <div className="w-full rounded-3xl border border-white/50 bg-white/45 backdrop-blur-2xl p-6 sm:p-10 shadow-[0_24px_70px_-12px_rgba(0,30,25,0.30)]">
      {showLogo && (
        <div className="mb-4 flex items-center gap-2.5">
          <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-white/60 p-1.5 shadow-sm border border-white/60 backdrop-blur-md">
            <ChatProSymbol size={28} glow />
          </div>
          <span className="text-sm font-bold tracking-wider text-emerald-950/80 uppercase">
            Chat<span className="text-brand font-black">PRO</span>
          </span>
        </div>
      )}
      <p className="text-xs sm:text-sm font-bold uppercase tracking-[0.18em] text-brand">{eyebrow}</p>
      <h1 className="mt-1 sm:mt-2 text-2xl sm:text-3xl font-bold tracking-tight text-txt-primary">{title}</h1>
      <p className="mt-1.5 sm:mt-2 text-xs sm:text-sm text-txt-muted leading-relaxed">{description}</p>
      {children}
      {footer}
    </div>
  )
}

export default AuthCard
