import { usePwaInstall } from '../hooks/usePwaInstall.js'

function InstallPwaButton({ className = '' }) {
  const { isInstallable, installPwa } = usePwaInstall()

  if (!isInstallable) {
    return null
  }

  return (
    <button
      type="button"
      onClick={installPwa}
      title="Install ChatPRO as an application"
      aria-label="Install ChatPRO application"
      className={`inline-flex items-center gap-1.5 rounded-xl border border-brand/30 bg-brand-soft px-2.5 py-2 sm:px-3 sm:py-2 text-xs font-semibold text-brand transition-all hover:border-brand hover:bg-brand-selected hover:shadow-xs ${className}`}
    >
      <svg
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="h-3.5 w-3.5 shrink-0"
        aria-hidden="true"
      >
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
        <polyline points="7 10 12 15 17 10" />
        <line x1="12" y1="15" x2="12" y2="3" />
      </svg>
      <span className="hidden sm:inline">Install ChatPRO</span>
      <span className="sm:hidden">Install</span>
    </button>
  )
}

export default InstallPwaButton
