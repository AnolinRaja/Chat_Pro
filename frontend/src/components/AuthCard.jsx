function AuthCard({ eyebrow, title, description, children, footer }) {
  return (
    <div className="w-full rounded-2xl border border-[#dbe5e1] bg-white p-5 shadow-[0_18px_50px_rgba(25,60,52,0.08)] sm:p-8">
      <p className="text-xs sm:text-sm font-semibold uppercase tracking-[0.18em] text-[#0f766e]">{eyebrow}</p>
      <h1 className="mt-2 sm:mt-3 text-2xl sm:text-3xl font-semibold tracking-tight text-[#172321]">{title}</h1>
      <p className="mt-1.5 sm:mt-2 text-xs sm:text-sm text-[#60736e] leading-relaxed">{description}</p>
      {children}
      {footer}
    </div>
  )
}

export default AuthCard
