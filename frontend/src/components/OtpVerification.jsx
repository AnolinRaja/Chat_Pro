import { useEffect, useRef, useState } from 'react'
import FormMessage from './FormMessage.jsx'

const OTP_LENGTH = 6
const DEFAULT_COOLDOWN_SECONDS = 60

function getSafeError(error, fallback) {
  const detail = error?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (error instanceof Error && error.message) return error.message
  return fallback
}

function OtpVerification({ email, onVerify, onResend, cooldownSeconds = DEFAULT_COOLDOWN_SECONDS }) {
  const [digits, setDigits] = useState(Array(OTP_LENGTH).fill(''))
  const [error, setError] = useState('')
  const [isVerifying, setIsVerifying] = useState(false)
  const [isResending, setIsResending] = useState(false)
  const [remainingSeconds, setRemainingSeconds] = useState(cooldownSeconds)
  const inputRefs = useRef([])

  useEffect(() => {
    if (remainingSeconds <= 0) return undefined
    const timer = window.setInterval(() => {
      setRemainingSeconds((current) => Math.max(0, current - 1))
    }, 1000)
    return () => window.clearInterval(timer)
  }, [remainingSeconds])

  const updateDigit = (index, value) => {
    const numericValue = value.replace(/\D/g, '').slice(-1)
    const nextDigits = [...digits]
    nextDigits[index] = numericValue
    setDigits(nextDigits)
    setError('')
    if (numericValue && index < OTP_LENGTH - 1) inputRefs.current[index + 1]?.focus()
  }

  const handlePaste = (event) => {
    event.preventDefault()
    const pastedDigits = event.clipboardData.getData('text').replace(/\D/g, '').slice(0, OTP_LENGTH)
    if (!pastedDigits) return
    setDigits([...Array(OTP_LENGTH)].map((_, index) => pastedDigits[index] || ''))
    setError('')
    inputRefs.current[Math.min(pastedDigits.length, OTP_LENGTH) - 1]?.focus()
  }

  const handleKeyDown = (event, index) => {
    if (event.key === 'Backspace' && !digits[index] && index > 0) {
      inputRefs.current[index - 1]?.focus()
    }
    if (event.key === 'ArrowLeft' && index > 0) inputRefs.current[index - 1]?.focus()
    if (event.key === 'ArrowRight' && index < OTP_LENGTH - 1) inputRefs.current[index + 1]?.focus()
  }

  const handleVerify = async (event) => {
    event.preventDefault()
    const otp = digits.join('')
    if (otp.length !== OTP_LENGTH) {
      setError('Enter the 6-digit verification code.')
      return
    }
    setError('')
    setIsVerifying(true)
    try {
      await onVerify(otp)
    } catch (verifyError) {
      setError(getSafeError(verifyError, 'Invalid verification code.'))
    } finally {
      setIsVerifying(false)
    }
  }

  const handleResend = async () => {
    if (remainingSeconds > 0 || isResending) return
    setError('')
    setIsResending(true)
    try {
      await onResend()
      setDigits(Array(OTP_LENGTH).fill(''))
      setRemainingSeconds(cooldownSeconds)
      inputRefs.current[0]?.focus()
    } catch (resendError) {
      setError(getSafeError(resendError, 'Unable to send verification code. Please try again.'))
    } finally {
      setIsResending(false)
    }
  }

  return (
    <div>
      <p className="text-xs sm:text-sm leading-6 text-[#60736e]">We&apos;ve sent a 6-digit verification code to</p>
      <p className="mt-1 truncate font-semibold text-[#172321]">{email}</p>
      <form className="mt-5 sm:mt-6 space-y-4 sm:space-y-5" onSubmit={handleVerify} noValidate>
        <FormMessage>{error}</FormMessage>
        <fieldset>
          <legend className="mb-2 text-xs sm:text-sm font-medium text-[#172321]">Verification code</legend>
          <div className="flex gap-1.5 sm:gap-3 justify-between" onPaste={handlePaste}>
            {digits.map((digit, index) => (
              <input
                key={`otp-${index}`}
                ref={(element) => { inputRefs.current[index] = element }}
                aria-label={`Verification code digit ${index + 1}`}
                inputMode="numeric"
                maxLength={1}
                pattern="[0-9]*"
                type="text"
                value={digit}
                onChange={(event) => updateDigit(index, event.target.value)}
                onKeyDown={(event) => handleKeyDown(event, index)}
                autoComplete={index === 0 ? 'one-time-code' : 'off'}
                className="h-11 sm:h-12 min-w-0 flex-1 max-w-12 rounded-lg border border-[#cddbd6] text-center text-base sm:text-lg font-bold font-mono outline-none focus:border-[#0f766e] focus:ring-2 focus:ring-[#99d6cc]"
              />
            ))}
          </div>
        </fieldset>
        <button
          disabled={isVerifying}
          type="submit"
          className="flex min-h-[44px] w-full items-center justify-center rounded-lg bg-[#0f766e] px-4 py-3 font-semibold text-white hover:bg-[#0b5f59] active:bg-[#084b46] disabled:cursor-not-allowed disabled:opacity-60 transition-colors"
        >
          {isVerifying ? 'Verifying...' : 'Verify code'}
        </button>
      </form>
      <div className="mt-5 text-center text-xs sm:text-sm text-[#60736e]">
        <p>Didn&apos;t receive the code?</p>
        <button
          type="button"
          disabled={remainingSeconds > 0 || isResending}
          onClick={handleResend}
          className="mt-1 inline-flex min-h-[36px] items-center justify-center font-semibold text-[#0f766e] hover:underline disabled:cursor-not-allowed disabled:no-underline disabled:opacity-50"
        >
          {isResending ? 'Sending...' : 'Resend OTP'}
        </button>
        {remainingSeconds > 0 && <p className="mt-1 text-xs">Resend available in {remainingSeconds} seconds</p>}
      </div>
    </div>
  )
}

export default OtpVerification
