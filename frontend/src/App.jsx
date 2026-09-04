import { useState } from 'react'
import { Link, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { useAuth } from './context/useAuth.js'
import InstallPwaButton from './components/InstallPwaButton.jsx'
import SecuritySettingsModal from './components/SecuritySettingsModal.jsx'
import ChatPage from './pages/ChatPage.jsx'
import ForgotPasswordPage from './pages/ForgotPasswordPage.jsx'
import LoginPage from './pages/LoginPage.jsx'
import RegisterPage from './pages/RegisterPage.jsx'

function ChatShellSkeleton() {
  return (
    <section className="mx-auto flex h-[calc(100dvh-57px)] sm:h-[calc(100vh-73px)] max-w-7xl overflow-hidden bg-white shadow-[0_18px_50px_rgba(25,60,52,0.08)] lg:my-6 lg:h-[calc(100vh-121px)] lg:rounded-2xl lg:border lg:border-[#dbe5e1]">
      {/* Workspace Rail Skeleton */}
      <div className="flex w-14 sm:w-16 shrink-0 flex-col items-center border-r border-[#dbe5e1] bg-[#edf3f1] py-3 sm:py-4 gap-2 sm:gap-2.5">
        <div className="h-10 w-10 sm:h-11 sm:w-11 rounded-2xl bg-[#d2e0dc] animate-pulse" />
        <div className="h-px w-6 sm:w-8 bg-[#cddbd6] my-0.5" />
        <div className="h-10 w-10 sm:h-11 sm:w-11 rounded-2xl bg-[#d2e0dc] animate-pulse" />
        <div className="h-10 w-10 sm:h-11 sm:w-11 rounded-2xl bg-[#d2e0dc] animate-pulse" />
      </div>

      {/* Sidebar Skeleton */}
      <div className="w-full sm:max-w-sm shrink-0 flex flex-col border-r border-[#dbe5e1] bg-[#fbfcfc]">
        <div className="border-b border-[#dbe5e1] px-3.5 sm:px-5 py-3.5 sm:py-5">
          <div className="h-3 w-20 rounded bg-[#cddbd6] animate-pulse" />
          <div className="mt-2 h-5 w-32 rounded bg-[#dbe5e1] animate-pulse" />
          <div className="mt-1 h-3 w-40 rounded bg-[#e8efed] animate-pulse" />
        </div>
        <div className="flex items-center justify-between px-3.5 sm:px-5 py-3 sm:py-4">
          <div className="h-4 w-28 rounded bg-[#cddbd6] animate-pulse" />
          <div className="h-7 w-20 rounded-lg bg-[#dbe5e1] animate-pulse" />
        </div>
        <div className="flex-1 px-3 space-y-2 py-2">
          <div className="flex items-center gap-3 p-2.5 rounded-xl bg-white border border-[#edf3f1] animate-pulse">
            <div className="h-10 w-10 rounded-full bg-[#dbe5e1]" />
            <div className="flex-1 space-y-2">
              <div className="h-3.5 w-3/4 rounded bg-[#dbe5e1]" />
              <div className="h-2.5 w-1/2 rounded bg-[#edf3f1]" />
            </div>
          </div>
          <div className="flex items-center gap-3 p-2.5 rounded-xl bg-white border border-[#edf3f1] animate-pulse">
            <div className="h-10 w-10 rounded-full bg-[#dbe5e1]" />
            <div className="flex-1 space-y-2">
              <div className="h-3.5 w-2/3 rounded bg-[#dbe5e1]" />
              <div className="h-2.5 w-1/3 rounded bg-[#edf3f1]" />
            </div>
          </div>
          <div className="flex items-center gap-3 p-2.5 rounded-xl bg-white border border-[#edf3f1] animate-pulse">
            <div className="h-10 w-10 rounded-full bg-[#dbe5e1]" />
            <div className="flex-1 space-y-2">
              <div className="h-3.5 w-1/2 rounded bg-[#dbe5e1]" />
              <div className="h-2.5 w-1/4 rounded bg-[#edf3f1]" />
            </div>
          </div>
        </div>
      </div>

      {/* Main Chat Area Skeleton */}
      <div className="min-w-0 flex-1 hidden sm:flex flex-col bg-[#eef4f2]">
        <div className="flex items-center justify-between border-b border-[#dbe5e1] bg-white px-3.5 py-3 sm:px-8 sm:py-4">
          <div className="space-y-1.5">
            <div className="h-4 w-36 rounded bg-[#dbe5e1] animate-pulse" />
            <div className="h-3 w-24 rounded bg-[#edf3f1] animate-pulse" />
          </div>
        </div>
        <div className="flex-1 flex flex-col justify-end gap-3 p-4 sm:p-8">
          <div className="flex justify-start">
            <div className="h-12 w-48 rounded-2xl rounded-bl-sm bg-white border border-[#e2ece9] animate-pulse" />
          </div>
          <div className="flex justify-end">
            <div className="h-10 w-40 rounded-2xl rounded-br-sm bg-[#cde8e3] animate-pulse" />
          </div>
          <div className="flex justify-start">
            <div className="h-14 w-64 rounded-2xl rounded-bl-sm bg-white border border-[#e2ece9] animate-pulse" />
          </div>
        </div>
        <div className="border-t border-[#dbe5e1] bg-white p-2.5 sm:p-4">
          <div className="h-11 rounded-xl bg-[#edf3f1] animate-pulse" />
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
    <div className="min-h-screen bg-[#f4f7f6] text-[#172321]">
      <header className="border-b border-[#dbe5e1] bg-white/90 pt-[env(safe-area-inset-top,0px)]">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-3 py-3 sm:px-8 sm:py-4">
          <Link to={user ? "/chat" : "/login"} className="flex items-center gap-2 sm:gap-3 shrink-0" aria-label="ChatPRO home">
            <span className="grid h-9 w-9 sm:h-10 sm:w-10 place-items-center rounded-xl bg-[#0f766e] text-base sm:text-lg font-bold text-white shadow-xs">C</span>
            <span className="text-lg sm:text-xl font-semibold tracking-tight">ChatPRO</span>
          </Link>
          <nav className="flex items-center gap-1.5 sm:gap-2 text-sm font-medium" aria-label="Primary navigation">
            <InstallPwaButton />
            {isLoading ? (
              <div className="h-8 w-20 rounded-lg bg-[#edf3f1] animate-pulse" />
            ) : user ? (
              <>
                <button
                  type="button"
                  onClick={() => setIsSecurityOpen(true)}
                  title="Security & Two-Step Verification"
                  aria-label="Security settings"
                  className="inline-flex items-center gap-1.5 rounded-lg border border-[#cddbd6] bg-white px-2.5 py-2 sm:px-3 sm:py-2 text-xs font-semibold text-[#48615c] hover:bg-[#edf5f2] hover:text-[#0f766e] transition-colors"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4 shrink-0">
                    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                  </svg>
                  <span className="hidden xs:inline sm:inline">Security</span>
                </button>
                <button
                  type="button"
                  onClick={logout}
                  className="rounded-lg bg-[#172321] px-2.5 py-2 sm:px-3 sm:py-2 text-xs sm:text-sm text-white hover:bg-[#2d413c] transition-colors"
                >
                  Log out
                </button>
              </>
            ) : (
              <>
                <Link to="/login" className="rounded-lg px-2.5 py-2 sm:px-3 sm:py-2 text-xs sm:text-sm text-[#48615c] hover:bg-[#edf5f2]">Sign in</Link>
                <Link to="/register" className="rounded-lg bg-[#172321] px-2.5 py-2 sm:px-3 sm:py-2 text-xs sm:text-sm text-white hover:bg-[#2d413c]">Create account</Link>
              </>
            )}
          </nav>
        </div>
      </header>
      <main>{children}</main>
      <SecuritySettingsModal isOpen={isSecurityOpen} onClose={() => setIsSecurityOpen(false)} />
    </div>
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
