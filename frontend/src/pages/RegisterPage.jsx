import { useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import AuthCard from '../components/AuthCard.jsx'
import FormMessage from '../components/FormMessage.jsx'
import OtpVerification from '../components/OtpVerification.jsx'
import { useAuth } from '../context/useAuth.js'
import { resendRegistration, verifyRegistration } from '../services/otpService.js'
import { validateRegistration } from '../utils/validation.js'

function RegisterPage() {
  const { user, register } = useAuth()
  const navigate = useNavigate()
  const [form, setForm] = useState({ name: '', email: '', password: '' })
  const [error, setError] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [verificationEmail, setVerificationEmail] = useState('')

  if (user) return <Navigate to="/chat" replace />

  const updateField = (event) => setForm({ ...form, [event.target.name]: event.target.value })

  const handleSubmit = async (event) => {
    event.preventDefault()
    const validationError = validateRegistration(form)
    if (validationError) return setError(validationError)
    setError('')
    setIsSubmitting(true)
    try {
      await register(form)
      setVerificationEmail(form.email)
    } catch (submitError) {
      setError(submitError.message)
    } finally {
      setIsSubmitting(false)
    }
  }

  if (verificationEmail) {
    return (
      <section className="mx-auto flex min-h-[calc(100vh-73px)] max-w-xl items-center px-4 py-8 sm:px-8 sm:py-12">
        <AuthCard eyebrow="Verify your account" title="Verify your email" description="Confirm your email to finish creating your ChatPRO account.">
          <OtpVerification
            email={verificationEmail}
            onVerify={async (otp) => {
              await verifyRegistration(verificationEmail, otp)
              navigate('/login', { replace: true })
            }}
            onResend={() => resendRegistration(verificationEmail)}
          />
        </AuthCard>
      </section>
    )
  }

  return (
    <section className="mx-auto flex min-h-[calc(100vh-73px)] max-w-xl items-center px-4 py-8 sm:px-8 sm:py-12">
      <AuthCard eyebrow="Start a new chapter" title="Create your ChatPRO account" description="A simple home for your everyday conversations.">
        <form className="mt-5 sm:mt-7 space-y-4 sm:space-y-5" onSubmit={handleSubmit} noValidate>
          <FormMessage>{error}</FormMessage>
          <label className="block text-sm font-medium text-[#172321]">
            Name
            <input
              name="name"
              type="text"
              value={form.name}
              onChange={updateField}
              autoComplete="name"
              placeholder="Your name"
              className="mt-1.5 sm:mt-2 w-full rounded-lg border border-[#cddbd6] px-3.5 py-2.5 sm:px-3 sm:py-3 text-base sm:text-sm outline-none focus:border-[#0f766e] focus:ring-2 focus:ring-[#99d6cc]"
            />
          </label>
          <label className="block text-sm font-medium text-[#172321]">
            Email
            <input
              name="email"
              type="email"
              value={form.email}
              onChange={updateField}
              autoComplete="email"
              placeholder="you@example.com"
              className="mt-1.5 sm:mt-2 w-full rounded-lg border border-[#cddbd6] px-3.5 py-2.5 sm:px-3 sm:py-3 text-base sm:text-sm outline-none focus:border-[#0f766e] focus:ring-2 focus:ring-[#99d6cc]"
            />
          </label>
          <label className="block text-sm font-medium text-[#172321]">
            Password
            <input
              name="password"
              type="password"
              value={form.password}
              onChange={updateField}
              autoComplete="new-password"
              placeholder="At least 8 characters"
              className="mt-1.5 sm:mt-2 w-full rounded-lg border border-[#cddbd6] px-3.5 py-2.5 sm:px-3 sm:py-3 text-base sm:text-sm outline-none focus:border-[#0f766e] focus:ring-2 focus:ring-[#99d6cc]"
            />
          </label>
          <button
            disabled={isSubmitting}
            type="submit"
            className="flex min-h-[44px] w-full items-center justify-center rounded-lg bg-[#172321] px-4 py-3 font-semibold text-white hover:bg-[#2d413c] active:bg-[#121c1a] disabled:cursor-not-allowed disabled:opacity-60 transition-colors"
          >
            {isSubmitting ? 'Creating account...' : 'Create account'}
          </button>
        </form>
        <p className="mt-5 sm:mt-6 text-center text-xs sm:text-sm text-[#60736e]">
          Already have an account?{' '}
          <Link to="/login" className="font-semibold text-[#0f766e] hover:underline">
            Sign in
          </Link>
        </p>
      </AuthCard>
    </section>
  )
}

export default RegisterPage
