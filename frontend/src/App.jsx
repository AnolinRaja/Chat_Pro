import { useState } from 'react'
import { Link, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { useAuth } from './context/useAuth.js'
import InstallPwaButton from './components/InstallPwaButton.jsx'
import SecuritySettingsModal from './components/SecuritySettingsModal.jsx'
import { ChatProSymbol } from './components/ChatProLogo.jsx'
import ChatPage from './pages/ChatPage.jsx'
import ForgotPasswordPage from './pages/ForgotPasswordPage.jsx'
import LoginPage from './pages/LoginPage.jsx'
import RegisterPage from './pages/RegisterPage.jsx'

function ChatShellSkeleton() {
  return (
    <section className="mx-auto flex h-[calc(100dvh-57px)] sm:h-[calc(100vh-73px)] max-w-7xl overflow-hidden bg-white/10 backdrop-blur-xl shadow-[0_24px_70px_-15px_rgba(0,30,25,0.35)] lg:my-6 lg:h-[calc(100vh-121px)] lg:rounded-3xl lg:border lg:border-white/30">
      {/* Workspace Rail Skeleton */}
      <div className="flex w-14 sm:w-16 shrink-0 flex-col items-center border-r border-white/30 bg-white/20 backdrop-blur-xl py-3 sm:py-4 gap-2 sm:gap-2.5">
        <div className="h-10 w-10 sm:h-11 sm:w-11 rounded-2xl bg-white/40 animate-pulse" />
        <div className="h-px w-6 sm:w-8 bg-white/30 my-0.5" />
        <div className="h-10 w-10 sm:h-11 sm:w-11 rounded-2xl bg-white/40 animate-pulse" />
        <div className="h-10 w-10 sm:h-11 sm:w-11 rounded-2xl bg-white/40 animate-pulse" />
      </div>

      {/* Sidebar Skeleton */}
      <div className="w-full sm:max-w-sm shrink-0 flex flex-col border-r border-white/30 bg-white/30 backdrop-blur-xl">
        <div className="border-b border-white/30 px-3.5 sm:px-5 py-3.5 sm:py-5 bg-white/20">
          <div className="h-3 w-20 rounded bg-white/50 animate-pulse" />
          <div className="mt-2 h-5 w-32 rounded bg-white/30 animate-pulse" />
          <div className="mt-1 h-3 w-40 rounded bg-white/30 animate-pulse" />
        </div>
        <div className="flex items-center justify-between px-3.5 sm:px-5 py-3 sm:py-4">
          <div className="h-4 w-28 rounded bg-white/50 animate-pulse" />
          <div className="h-7 w-20 rounded-lg bg-white/30 animate-pulse" />
        </div>
        <div className="flex-1 px-3 space-y-2 py-2">
          <div className="flex items-center gap-3 p-2.5 rounded-xl bg-white/40 border border-white/30 animate-pulse">
            <div className="h-10 w-10 rounded-full bg-white/50" />
            <div className="flex-1 space-y-2">
              <div className="h-3.5 w-3/4 rounded bg-white/50" />
              <div className="h-2.5 w-1/2 rounded bg-white/30" />
            </div>
          </div>
          <div className="flex items-center gap-3 p-2.5 rounded-xl bg-white/40 border border-white/30 animate-pulse">
            <div className="h-10 w-10 rounded-full bg-white/50" />
            <div className="flex-1 space-y-2">
              <div className="h-3.5 w-2/3 rounded bg-white/50" />
              <div className="h-2.5 w-1/3 rounded bg-white/30" />
            </div>
          </div>
        </div>
      </div>

      {/* Main Chat Area Skeleton */}
      <div className="min-w-0 flex-1 hidden sm:flex flex-col bg-white/5 backdrop-blur-xs">
        <div className="flex items-center justify-between border-b border-white/30 bg-white/35 backdrop-blur-xl px-3.5 py-3 sm:px-8 sm:py-4">
          <div className="space-y-1.5">
            <div className="h-4 w-36 rounded bg-white/50 animate-pulse" />
            <div className="h-3 w-24 rounded bg-white/30 animate-pulse" />
          </div>
        </div>
        <div className="flex-1 flex flex-col justify-end gap-3 p-4 sm:p-8">
          <div className="flex justify-start">
            <div className="h-12 w-48 rounded-2xl rounded-bl-xs bg-white/50 border border-white/30 animate-pulse" />
          </div>
          <div className="flex justify-end">
            <div className="h-10 w-40 rounded-2xl rounded-br-xs bg-brand-soft animate-pulse" />
          </div>
        </div>
        <div className="border-t border-white/30 bg-white/20 p-2.5 sm:p-4">
          <div className="h-11 rounded-xl bg-white/40 animate-pulse" />
        </div>
      </div>
    </section>
  )
}

function ProtectedRoute({ children }) {
  const { user, isLoading } = useAuth()
  const location = useLocation()

  if (isLoading) {
    return <ChatShellSkeleton />
  }

  return user ? children : <Navigate to="/login" replace state={{ from: location }} />
}

function AppShell({ children }) {
  const { user, isLoading, logout } = useAuth()
  const [isSecurityOpen, setIsSecurityOpen] = useState(false)

  return (
    <>
      <div className="chatpro-ambient-bg" aria-hidden="true" />
      <div className="relative z-10 min-h-screen text-txt-primary flex flex-col">
        <header className="sticky top-0 z-30 border-b border-white/30 bg-white/35 backdrop-blur-xl pt-[env(safe-area-inset-top,0px)] shadow-[0_4px_24px_rgba(0,30,25,0.15)]">
          <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3 sm:px-8 sm:py-3.5">
            <Link to={user ? "/chat" : "/login"} className="flex items-center gap-2.5 sm:gap-3 shrink min-w-0 max-w-[65%] sm:max-w-[75%] group" aria-label="ChatPRO home">
              <div className="grid place-items-center rounded-2xl bg-white/40 p-1.5 backdrop-blur-md border border-white/50 shadow-xs group-hover:scale-105 transition-all">
                <ChatProSymbol size={28} glow />
              </div>
              <span className="text-base sm:text-xl font-bold tracking-tight text-txt-primary leading-tight font-display truncate">
                {user?.name ? `${user.name}'s ` : ''}<span className="text-teal-800">chat</span><span className="text-brand font-black">PRO</span>
              </span>
            </Link>
            <nav className="flex items-center gap-2 sm:gap-3 text-sm font-medium" aria-label="Primary navigation">
              <InstallPwaButton />

              {/* Floating Glass Pill for Quick Controls */}
              <div className="hidden sm:flex items-center gap-1 rounded-full border border-white/40 bg-white/40 backdrop-blur-md px-2.5 py-1 shadow-xs">
                <span className="text-xs text-txt-secondary" title="Light mode active" aria-label="Light mode">☀️</span>
                <span className="text-xs opacity-40">/</span>
                <span className="text-xs opacity-50" title="Dark mode available" aria-label="Dark mode">🌙</span>
              </div>

              {isLoading ? (
                <div className="h-9 w-20 rounded-xl bg-line-subtle animate-pulse" />
              ) : user ? (
                <>
                  <button
                    type="button"
                    onClick={() => setIsSecurityOpen(true)}
                    title="Security & Two-Step Verification"
                    aria-label="Security settings"
                    className="relative inline-flex items-center gap-1.5 rounded-xl border border-white/40 bg-white/40 px-3 py-2 text-xs font-semibold text-txt-secondary hover:bg-white/70 hover:text-brand hover:border-brand/40 transition-all shadow-xs backdrop-blur-md"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4 shrink-0">
                      <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
                      <path d="M13.73 21a2 2 0 0 1-3.46 0" />
                    </svg>
                    <span className="hidden xs:inline sm:inline">Settings</span>
                  </button>
                  <button
                    type="button"
                    onClick={logout}
                    className="rounded-xl bg-txt-primary px-3 py-2 text-xs sm:text-sm font-semibold text-white hover:bg-txt-secondary transition-all shadow-xs"
                  >
                    Log out
                  </button>
                </>
              ) : (
                <>
                  <Link to="/login" className="rounded-xl px-3.5 py-2 text-xs sm:text-sm font-semibold text-txt-secondary hover:bg-brand-soft hover:text-brand transition-all">Sign in</Link>
                  <Link to="/register" className="rounded-xl bg-gradient-to-r from-[#0f766e] to-[#0c635c] px-3.5 py-2 text-xs sm:text-sm font-bold text-white hover:brightness-110 shadow-sm transition-all">Create account</Link>
                </>
              )}
            </nav>
          </div>
        </header>
        <main className="flex-1 flex flex-col">{children}</main>
        <SecuritySettingsModal isOpen={isSecurityOpen} onClose={() => setIsSecurityOpen(false)} />
      </div>
    </>
  )
}

function App() {
  const { user, isLoading } = useAuth()

  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<Navigate to={user ? "/chat" : "/login"} replace />} />
        <Route path="/login" element={!isLoading && user ? <Navigate to="/chat" replace /> : <LoginPage />} />
        <Route path="/forgot-password" element={!isLoading && user ? <Navigate to="/chat" replace /> : <ForgotPasswordPage />} />
        <Route path="/register" element={!isLoading && user ? <Navigate to="/chat" replace /> : <RegisterPage />} />
        <Route path="/chat" element={<ProtectedRoute><ChatPage /></ProtectedRoute>} />
        <Route path="*" element={<Navigate to={user ? "/chat" : "/login"} replace />} />
      </Routes>
    </AppShell>
  )
}

export default App
