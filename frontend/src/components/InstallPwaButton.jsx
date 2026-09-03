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
      className={`inline-flex items-center gap-1.5 rounded-lg border border-[#0f766e]/30 bg-[#d9f0eb]/70 px-3 py-1.5 text-xs font-semibold text-[#0f766e] transition-all hover:border-[#0f766e] hover:bg-[#d9f0eb] hover:shadow-sm ${className}`}
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
      <span>Install ChatPRO</span>
    </button>
  )
}

export default InstallPwaButton
