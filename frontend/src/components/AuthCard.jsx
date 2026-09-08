function AuthCard({ eyebrow, title, description, children, footer }) {
  return (
    <div className="w-full rounded-2xl border border-line-glass bg-glass-card p-5 sm:p-8 shadow-glass">
      <p className="text-xs sm:text-sm font-semibold uppercase tracking-[0.18em] text-brand">{eyebrow}</p>
      <h1 className="mt-2 sm:mt-3 text-2xl sm:text-3xl font-semibold tracking-tight text-txt-primary">{title}</h1>
      <p className="mt-1.5 sm:mt-2 text-xs sm:text-sm text-txt-muted leading-relaxed">{description}</p>
      {children}
      {footer}
    </div>
  )
}

export default AuthCard
