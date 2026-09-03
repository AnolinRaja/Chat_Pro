import { useState } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import AuthCard from '../components/AuthCard.jsx'
import FormMessage from '../components/FormMessage.jsx'
import OtpVerification from '../components/OtpVerification.jsx'
import { useAuth } from '../context/useAuth.js'
import { resendLogin, resendRegistration, verifyRegistration } from '../services/otpService.js'
import { validateLogin } from '../utils/validation.js'

function LoginPage() {
  const { user, login, verifyLogin, verify2SV } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [form, setForm] = useState({ email: '', password: '' })
  const [error, setError] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [otpEmail, setOtpEmail] = useState('')
  const [otpPurpose, setOtpPurpose] = useState('login')

  // 2SV state
  const [twoFactorToken, setTwoFactorToken] = useState('')
  const [twoFactorCode, setTwoFactorCode] = useState('')
  const [isRecoveryMode, setIsRecoveryMode] = useState(false)

  if (user) return <Navigate to="/chat" replace />

  const updateField = (event) => setForm({ ...form, [event.target.name]: event.target.value })

  const handleSubmit = async (event) => {
    event.preventDefault()
    const validationError = validateLogin(form)
    if (validationError) return setError(validationError)
    setError('')
    setIsSubmitting(true)
    try {
      const result = await login({ email: form.email, password: form.password })
      if (result?.requires_2sv) {
        setTwoFactorToken(result.two_factor_token)
        setTwoFactorCode('')
        setIsRecoveryMode(false)
      } else if (result?.requires_otp) {
        setOtpEmail(result.email)
        setOtpPurpose(result.purpose || 'login')
      } else if (result?.access_token) {
        navigate(location.state?.from?.pathname || '/chat', { replace: true })
      }
    } catch (submitError) {
      setError(submitError.message)
    } finally {
      setIsSubmitting(false)
    }
  }

  const handle2SVSubmit = async (event) => {
    event.preventDefault()
    if (!twoFactorCode.trim()) {
      return setError(isRecoveryMode ? 'Please enter a recovery code.' : 'Please enter your 6-digit verification code.')
    }
    setError('')
    setIsSubmitting(true)
    try {
      await verify2SV(twoFactorToken, twoFactorCode.trim())
      navigate(location.state?.from?.pathname || '/chat', { replace: true })
    } catch (err) {
      setError(err.message)
    } finally {
      setIsSubmitting(false)
    }
  }

  // 2SV Challenge UI
  if (twoFactorToken) {
    return (
      <section className="mx-auto flex min-h-[calc(100vh-73px)] max-w-xl items-center px-5 py-12 sm:px-8">
        <AuthCard
          eyebrow="Two-Step Verification"
          title={isRecoveryMode ? 'Use a Recovery Code' : 'Enter Verification Code'}
          description={
            isRecoveryMode
              ? 'Enter one of your emergency backup recovery codes to sign in.'
              : 'Enter the 6-digit code from your authenticator app (Google Authenticator, Apple Passwords, Authy, etc.).'
          }
        >
          <form className="mt-7 space-y-5" onSubmit={handle2SVSubmit} noValidate>
            <FormMessage>{error}</FormMessage>
            <label className="block text-sm font-medium">
              {isRecoveryMode ? 'Emergency Recovery Code' : '6-Digit Authenticator Code'}
              <input
                type="text"
                value={twoFactorCode}
                onChange={(e) => setTwoFactorCode(e.target.value)}
                placeholder={isRecoveryMode ? 'e.g. 1a2b-3c4d' : '123456'}
                maxLength={isRecoveryMode ? 20 : 8}
                autoFocus
                className="mt-2 w-full rounded-lg border border-[#cddbd6] px-3 py-3 text-center text-lg font-mono tracking-widest outline-none focus:border-[#0f766e] focus:ring-2 focus:ring-[#99d6cc]"
              />
            </label>

            <button
              disabled={isSubmitting}
              type="submit"
              className="w-full rounded-lg bg-[#0f766e] px-4 py-3 font-semibold text-white hover:bg-[#0b5f59] disabled:cursor-not-allowed disabled:opacity-60 transition-colors"
            >
              {isSubmitting ? 'Verifying...' : 'Verify & Sign In'}
            </button>

            <div className="flex items-center justify-between text-xs text-[#60736e]">
              <button
                type="button"
                onClick={() => {
                  setIsRecoveryMode(!isRecoveryMode)
                  setTwoFactorCode('')
                  setError('')
                }}
                className="font-medium text-[#0f766e] hover:underline"
              >
                {isRecoveryMode ? '← Use Authenticator App Code' : "Can't access your authenticator? Use recovery code"}
              </button>
              <button
                type="button"
                onClick={() => {
                  setTwoFactorToken('')
                  setTwoFactorCode('')
                  setError('')
                }}
                className="text-[#60736e] hover:underline"
              >
                Back to Sign in
              </button>
            </div>
          </form>
        </AuthCard>
      </section>
    )
  }

  // Registration OTP UI
  if (otpEmail) {
    return (
      <section className="mx-auto flex min-h-[calc(100vh-73px)] max-w-xl items-center px-5 py-12 sm:px-8">
        <AuthCard eyebrow="Secure sign in" title="Verify your email" description="Complete verification to continue to ChatPRO.">
          <OtpVerification
            email={otpEmail}
            onVerify={async (otp) => {
              if (otpPurpose === 'registration') {
                await verifyRegistration(otpEmail, otp)
                setOtpPurpose('login')
                const result = await login({ email: otpEmail, password: form.password })
                if (result?.requires_otp) return
                if (result?.requires_2sv) {
                  setTwoFactorToken(result.two_factor_token)
                  setOtpEmail('')
                  return
                }
              } else {
                await verifyLogin(otpEmail, otp)
              }
              navigate(location.state?.from?.pathname || '/chat', { replace: true })
            }}
            onResend={() => (otpPurpose === 'registration' ? resendRegistration(otpEmail) : resendLogin(otpEmail))}
          />
        </AuthCard>
      </section>
    )
  }

  return (
    <section className="mx-auto grid min-h-[calc(100vh-73px)] max-w-6xl items-center gap-12 px-5 py-12 sm:px-8 lg:grid-cols-[1.1fr_0.9fr]">
      <div className="max-w-xl">
        <p className="mb-5 text-sm font-semibold uppercase tracking-[0.18em] text-[#0f766e]">Your conversations, in focus</p>
        <h2 className="text-5xl font-semibold leading-[1.05] tracking-tight text-[#172321] sm:text-7xl">A calmer place to stay connected.</h2>
        <p className="mt-6 max-w-md text-lg leading-8 text-[#60736e]">ChatPRO keeps the people and conversations that matter close, clear, and easy to reach.</p>
      </div>
      <AuthCard eyebrow="Welcome back" title="Sign in to ChatPRO" description="Continue to your conversations.">
        <form className="mt-7 space-y-5" onSubmit={handleSubmit} noValidate>
          <FormMessage>{error}</FormMessage>
          <label className="block text-sm font-medium">
            Email
            <input
              name="email"
              type="email"
              value={form.email}
              onChange={updateField}
              autoComplete="email"
              placeholder="you@example.com"
              className="mt-2 w-full rounded-lg border border-[#cddbd6] px-3 py-3 outline-none focus:border-[#0f766e] focus:ring-2 focus:ring-[#99d6cc]"
            />
          </label>
          <label className="block text-sm font-medium">
            Password
            <input
              name="password"
              type="password"
              value={form.password}
              onChange={updateField}
              autoComplete="current-password"
              placeholder="Enter your password"
              className="mt-2 w-full rounded-lg border border-[#cddbd6] px-3 py-3 outline-none focus:border-[#0f766e] focus:ring-2 focus:ring-[#99d6cc]"
            />
          </label>
          <p className="text-right text-sm">
            <Link to="/forgot-password" className="font-semibold text-[#0f766e] hover:underline">
              Forgot Password?
            </Link>
          </p>
          <button
            disabled={isSubmitting}
            type="submit"
            className="w-full rounded-lg bg-[#0f766e] px-4 py-3 font-semibold text-white hover:bg-[#0b5f59] disabled:cursor-not-allowed disabled:opacity-60 transition-colors"
          >
            {isSubmitting ? 'Signing in...' : 'Sign in'}
          </button>
        </form>
        <p className="mt-6 text-center text-sm text-[#60736e]">
          New to ChatPRO?{' '}
          <Link to="/register" className="font-semibold text-[#0f766e] hover:underline">
            Create an account
          </Link>
        </p>
      </AuthCard>
    </section>
  )
}

export default LoginPage
