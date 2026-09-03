import { useState } from 'react'
import { Link, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { useAuth } from './context/useAuth.js'
import InstallPwaButton from './components/InstallPwaButton.jsx'
import SecuritySettingsModal from './components/SecuritySettingsModal.jsx'
import ChatPage from './pages/ChatPage.jsx'
import ForgotPasswordPage from './pages/ForgotPasswordPage.jsx'
import LoginPage from './pages/LoginPage.jsx'
import RegisterPage from './pages/RegisterPage.jsx'

function ProtectedRoute({ children }) {
  const { user, isLoading } = useAuth()
  const location = useLocation()

  if (isLoading) {
    return <div className="grid min-h-[calc(100vh-73px)] place-items-center text-sm text-[#60736e]">Restoring your session...</div>
  }

  return user ? children : <Navigate to="/login" replace state={{ from: location }} />
}

function AppShell({ children }) {
  const { user, logout } = useAuth()
  const [isSecurityOpen, setIsSecurityOpen] = useState(false)

  return (
    <div className="min-h-screen bg-[#f4f7f6] text-[#172321]">
      <header className="border-b border-[#dbe5e1] bg-white/90">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-4 sm:px-8">
          <Link to="/login" className="flex items-center gap-3" aria-label="ChatPRO home">
            <span className="grid h-10 w-10 place-items-center rounded-xl bg-[#0f766e] text-lg font-bold text-white">C</span>
            <span className="text-xl font-semibold tracking-tight">ChatPRO</span>
          </Link>
          <nav className="flex items-center gap-2 text-sm font-medium" aria-label="Primary navigation">
            <InstallPwaButton />
            {user ? (
              <>
                <button
                  type="button"
                  onClick={() => setIsSecurityOpen(true)}
                  title="Security & Two-Step Verification"
                  aria-label="Security settings"
                  className="inline-flex items-center gap-1.5 rounded-lg border border-[#cddbd6] bg-white px-3 py-2 text-xs font-semibold text-[#48615c] hover:bg-[#edf5f2] hover:text-[#0f766e]"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-3.5 w-3.5">
                    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                  </svg>
                  <span>Security</span>
                </button>
                <button
                  type="button"
                  onClick={logout}
                  className="rounded-lg bg-[#172321] px-3 py-2 text-white hover:bg-[#2d413c]"
                >
                  Log out
                </button>
              </>
            ) : (
              <>
                <Link to="/login" className="rounded-lg px-3 py-2 text-[#48615c] hover:bg-[#edf5f2]">Sign in</Link>
                <Link to="/register" className="rounded-lg bg-[#172321] px-3 py-2 text-white hover:bg-[#2d413c]">Create account</Link>
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
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<Navigate to="/login" replace />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/chat" element={<ProtectedRoute><ChatPage /></ProtectedRoute>} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </AppShell>
  )
}

export default App
