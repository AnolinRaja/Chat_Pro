import { useState } from 'react'
import { Link } from 'react-router-dom'
import AuthCard from '../components/AuthCard.jsx'
import FormMessage from '../components/FormMessage.jsx'
import OtpVerification from '../components/OtpVerification.jsx'
import { completePasswordReset, requestPasswordReset, verifyPasswordReset } from '../services/otpService.js'
import { validateEmail } from '../utils/validation.js'

function getSafeError(error, fallback) {
  const status = error?.response?.status
  if (status === 401) return 'Invalid verification code.'
  if (status === 429) return 'Too many attempts. Please try again later.'
  if (status === 422) return 'Please check the information and try again.'
  return fallback
}

function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [error, setError] = useState('')
  const [step, setStep] = useState('email')
  const [resetToken, setResetToken] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  const handleSubmit = async (event) => {
    event.preventDefault()
    if (!email || !validateEmail(email)) {
      setError('Enter a valid email address.')
      return
    }
    setError('')
    setIsSubmitting(true)
    try {
      await requestPasswordReset(email)
      setStep('otp')
    } catch (submitError) {
      setError(getSafeError(submitError, 'Unable to send verification code. Please try again.'))
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleVerify = async (otp) => {
    try {
      const result = await verifyPasswordReset(email, otp)
      setResetToken(result.reset_token)
      setStep('password')
    } catch (verifyError) {
      throw new Error(getSafeError(verifyError, 'Invalid verification code.'), { cause: verifyError })
    }
  }

  const handleReset = async (event) => {
    event.preventDefault()
    if (newPassword.length < 8) return setError('Password must be at least 8 characters.')
    if (newPassword !== confirmPassword) return setError('Passwords do not match.')
    setError('')
    setIsSubmitting(true)
    try {
      await completePasswordReset(resetToken, newPassword)
      setStep('complete')
    } catch (resetError) {
      setError(getSafeError(resetError, 'Unable to reset your password. Please try again.'))
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <section className="mx-auto flex min-h-[calc(100vh-73px)] max-w-xl items-center px-5 py-12 sm:px-8">
      <AuthCard eyebrow="Account recovery" title={step === 'complete' ? 'Password reset complete' : 'Forgot your password?'} description={step === 'complete' ? 'Your password has been updated.' : 'Enter your email to begin secure account recovery.'}>
        {step === 'otp' && <OtpVerification email={email} onVerify={handleVerify} onResend={() => requestPasswordReset(email)} />}
        {step === 'password' && <form className="mt-7 space-y-5" onSubmit={handleReset} noValidate><FormMessage>{error}</FormMessage><label className="block text-sm font-medium">New password<input type="password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} autoComplete="new-password" className="mt-2 w-full rounded-lg border border-[#cddbd6] px-3 py-3 outline-none focus:border-[#0f766e] focus:ring-2 focus:ring-[#99d6cc]" /></label><label className="block text-sm font-medium">Confirm password<input type="password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} autoComplete="new-password" className="mt-2 w-full rounded-lg border border-[#cddbd6] px-3 py-3 outline-none focus:border-[#0f766e] focus:ring-2 focus:ring-[#99d6cc]" /></label><button disabled={isSubmitting} type="submit" className="w-full rounded-lg bg-[#0f766e] px-4 py-3 font-semibold text-white hover:bg-[#0b5f59] disabled:cursor-not-allowed disabled:opacity-60">{isSubmitting ? 'Updating...' : 'Set new password'}</button></form>}
        {step === 'complete' && <p className="mt-7 text-center text-sm text-[#60736e]"><Link to="/login" className="font-semibold text-[#0f766e] hover:underline">Return to sign in</Link></p>}
        {step === 'email' && <>
        <form className="mt-7 space-y-5" onSubmit={handleSubmit} noValidate>
          <FormMessage>{error}</FormMessage>
          <label className="block text-sm font-medium">Email<input name="email" type="email" value={email} onChange={(event) => { setEmail(event.target.value); setError('') }} autoComplete="email" placeholder="you@example.com" className="mt-2 w-full rounded-lg border border-[#cddbd6] px-3 py-3 outline-none focus:border-[#0f766e] focus:ring-2 focus:ring-[#99d6cc]" /></label>
          <button disabled={isSubmitting} type="submit" className="w-full rounded-lg bg-[#0f766e] px-4 py-3 font-semibold text-white hover:bg-[#0b5f59] disabled:cursor-not-allowed disabled:opacity-60">{isSubmitting ? 'Sending...' : 'Continue'}</button>
        </form>
        <p className="mt-6 text-center text-sm text-[#60736e]"><Link to="/login" className="font-semibold text-[#0f766e] hover:underline">Return to sign in</Link></p>
        </>}
      </AuthCard>
    </section>
  )
}

export default ForgotPasswordPage
