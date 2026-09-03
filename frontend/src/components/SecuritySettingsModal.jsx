import { useEffect, useState } from 'react'
import { useAuth } from '../context/useAuth.js'
import { confirm2SV, disable2SV, get2SVStatus, setup2SV } from '../services/authService.js'

function SecuritySettingsModal({ isOpen, onClose }) {
  const { refreshUser } = useAuth()
  const [statusLoading, setStatusLoading] = useState(true)
  const [twoFactorEnabled, setTwoFactorEnabled] = useState(false)
  const [recoveryCodesRemaining, setRecoveryCodesRemaining] = useState(0)
  const [error, setError] = useState('')
  const [successMessage, setSuccessMessage] = useState('')

  // Setup wizard state
  const [isSettingUp, setIsSettingUp] = useState(false)
  const [setupLoading, setSetupLoading] = useState(false)
  const [setupData, setSetupData] = useState(null) // { secret, otpauth_uri, recovery_codes }
  const [confirmCode, setConfirmCode] = useState('')
  const [copiedKey, setCopiedKey] = useState(false)
  const [copiedCodes, setCopiedCodes] = useState(false)

  // Disable dialog state
  const [isDisabling, setIsDisabling] = useState(false)
  const [disablePassword, setDisablePassword] = useState('')
  const [disableCode, setDisableCode] = useState('')
  const [actionLoading, setActionLoading] = useState(false)

  useEffect(() => {
    if (!isOpen) return

    let active = true
    get2SVStatus()
      .then((data) => {
        if (active) {
          setTwoFactorEnabled(data.two_factor_enabled)
          setRecoveryCodesRemaining(data.recovery_codes_remaining)
          setStatusLoading(false)
        }
      })
      .catch((err) => {
        if (active) {
          setError(err.response?.data?.detail || 'Unable to load security status.')
          setStatusLoading(false)
        }
      })

    return () => {
      active = false
    }
  }, [isOpen])

  if (!isOpen) return null

  const handleClose = () => {
    setIsSettingUp(false)
    setIsDisabling(false)
    setSetupData(null)
    setConfirmCode('')
    setDisablePassword('')
    setDisableCode('')
    setError('')
    setSuccessMessage('')
    onClose()
  }

  const handleStartSetup = async () => {
    setSetupLoading(true)
    setError('')
    setSuccessMessage('')
    try {
      const data = await setup2SV()
      setSetupData(data)
      setIsSettingUp(true)
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to initialize Two-Step Verification.')
    } finally {
      setSetupLoading(false)
    }
  }

  const handleConfirmSetup = async (e) => {
    e.preventDefault()
    if (!confirmCode.trim()) {
      return setError('Please enter the 6-digit verification code.')
    }
    setActionLoading(true)
    setError('')
    try {
      await confirm2SV(confirmCode.trim())
      setSuccessMessage('Two-Step Verification has been enabled successfully!')
      setIsSettingUp(false)
      setSetupData(null)
      setConfirmCode('')
      await refreshUser()
      const data = await get2SVStatus()
      setTwoFactorEnabled(data.two_factor_enabled)
      setRecoveryCodesRemaining(data.recovery_codes_remaining)
    } catch (err) {
      setError(err.response?.data?.detail || 'Invalid verification code. Please check your authenticator app.')
    } finally {
      setActionLoading(false)
    }
  }

  const handleDisable2SV = async (e) => {
    e.preventDefault()
    if (!disablePassword) {
      return setError('Please enter your account password.')
    }
    if (!disableCode.trim()) {
      return setError('Please enter your current authenticator code or recovery code.')
    }
    setActionLoading(true)
    setError('')
    try {
      await disable2SV(disablePassword, disableCode.trim())
      setSuccessMessage('Two-Step Verification has been disabled.')
      setIsDisabling(false)
      setDisablePassword('')
      setDisableCode('')
      await refreshUser()
      const data = await get2SVStatus()
      setTwoFactorEnabled(data.two_factor_enabled)
      setRecoveryCodesRemaining(data.recovery_codes_remaining)
    } catch (err) {
      setError(err.response?.data?.detail || 'Unable to disable Two-Step Verification.')
    } finally {
      setActionLoading(false)
    }
  }

  const copySecret = () => {
    if (setupData?.secret) {
      navigator.clipboard.writeText(setupData.secret)
      setCopiedKey(true)
      setTimeout(() => setCopiedKey(false), 2000)
    }
  }

  const copyRecoveryCodes = () => {
    if (setupData?.recovery_codes) {
      navigator.clipboard.writeText(setupData.recovery_codes.join('\n'))
      setCopiedCodes(true)
      setTimeout(() => setCopiedCodes(false), 2000)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-xs">
      <div className="relative w-full max-w-xl max-h-[90vh] overflow-y-auto rounded-2xl border border-[#cddbd6] bg-white p-6 shadow-2xl sm:p-8">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-[#e2ece9] pb-4">
          <div className="flex items-center gap-2.5">
            <span className="grid h-9 w-9 place-items-center rounded-xl bg-[#0f766e]/10 text-[#0f766e]">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
              </svg>
            </span>
            <div>
              <h3 className="text-lg font-bold tracking-tight text-[#172321]">Security & Two-Step Verification</h3>
              <p className="text-xs text-[#60736e]">Protect your ChatPRO account with authenticator-based 2SV</p>
            </div>
          </div>
          <button
            type="button"
            onClick={handleClose}
            className="rounded-lg p-1.5 text-[#60736e] hover:bg-[#edf5f2] hover:text-[#172321]"
            aria-label="Close modal"
          >
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* Feedback Messages */}
        {error && (
          <div className="mt-4 rounded-lg bg-red-50 p-3 text-xs font-medium text-red-700 border border-red-200">
            {error}
          </div>
        )}
        {successMessage && (
          <div className="mt-4 rounded-lg bg-emerald-50 p-3 text-xs font-medium text-emerald-700 border border-emerald-200">
            {successMessage}
          </div>
        )}

        {/* Main Content */}
        {statusLoading ? (
          <div className="py-12 text-center text-sm text-[#60736e]">Loading security settings...</div>
        ) : isSettingUp && setupData ? (
          /* SETUP WIZARD */
          <div className="mt-6 space-y-6">
            <div>
              <span className="text-xs font-bold uppercase tracking-wider text-[#0f766e]">Step 1 of 3</span>
              <h4 className="text-base font-semibold text-[#172321]">Scan QR Code in Authenticator App</h4>
              <p className="mt-1 text-xs text-[#60736e]">
                Use Google Authenticator, Apple Passwords, Microsoft Authenticator, Authy, or 1Password. (Authenticator apps work offline and do not rely on email).
              </p>
            </div>

            {/* QR Code & Key Box */}
            <div className="flex flex-col items-center justify-center gap-4 rounded-xl border border-[#d2e0dc] bg-[#f8faf9] p-5 sm:flex-row">
              <img
                src={`https://api.qrserver.com/v1/create-qr-code/?size=150x150&data=${encodeURIComponent(setupData.otpauth_uri)}`}
                alt="2SV QR Code"
                className="h-36 w-36 rounded-lg border border-[#cddbd6] bg-white p-1.5 shadow-xs"
              />
              <div className="flex flex-1 flex-col gap-2 text-left">
                <span className="text-xs font-medium text-[#48615c]">Can't scan QR code? Enter key manually:</span>
                <div className="flex items-center gap-2">
                  <code className="rounded-md border border-[#cddbd6] bg-white px-2.5 py-1.5 font-mono text-xs font-bold text-[#172321] select-all">
                    {setupData.secret}
                  </code>
                  <button
                    type="button"
                    onClick={copySecret}
                    className="rounded-md bg-[#0f766e] px-2.5 py-1.5 text-xs font-semibold text-white hover:bg-[#0b5f59]"
                  >
                    {copiedKey ? 'Copied!' : 'Copy'}
                  </button>
                </div>
                <a
                  href={setupData.otpauth_uri}
                  className="mt-1 text-xs font-medium text-[#0f766e] hover:underline"
                >
                  Open in Authenticator app →
                </a>
              </div>
            </div>

            {/* Recovery Codes Step */}
            <div>
              <span className="text-xs font-bold uppercase tracking-wider text-[#0f766e]">Step 2 of 3</span>
              <h4 className="text-base font-semibold text-[#172321]">Save Emergency Backup Recovery Codes</h4>
              <p className="mt-1 text-xs text-[#60736e]">
                If you ever lose access to your authenticator app, these single-use codes are the only way to sign in. Save them in a secure password manager.
              </p>
              <div className="mt-3 rounded-xl border border-[#d2e0dc] bg-[#f8faf9] p-4">
                <div className="grid grid-cols-2 gap-2 font-mono text-xs font-semibold text-[#172321] sm:grid-cols-4">
                  {setupData.recovery_codes.map((code) => (
                    <div key={code} className="rounded bg-white p-1.5 text-center border border-[#e2ece9]">
                      {code}
                    </div>
                  ))}
                </div>
                <div className="mt-3 flex justify-end">
                  <button
                    type="button"
                    onClick={copyRecoveryCodes}
                    className="rounded-lg border border-[#cddbd6] bg-white px-3 py-1.5 text-xs font-semibold text-[#0f766e] hover:bg-[#edf5f2]"
                  >
                    {copiedCodes ? 'Codes Copied!' : 'Copy All Recovery Codes'}
                  </button>
                </div>
              </div>
            </div>

            {/* Confirmation Step */}
            <form onSubmit={handleConfirmSetup} className="space-y-4">
              <div>
                <span className="text-xs font-bold uppercase tracking-wider text-[#0f766e]">Step 3 of 3</span>
                <h4 className="text-base font-semibold text-[#172321]">Confirm Verification Code</h4>
                <p className="mt-1 text-xs text-[#60736e]">
                  Enter the current 6-digit code displayed in your authenticator app to complete setup:
                </p>
                <input
                  type="text"
                  value={confirmCode}
                  onChange={(e) => setConfirmCode(e.target.value)}
                  placeholder="123456"
                  maxLength={8}
                  autoFocus
                  className="mt-2 w-full rounded-lg border border-[#cddbd6] px-3 py-2.5 text-center font-mono text-lg font-bold tracking-widest outline-none focus:border-[#0f766e] focus:ring-2 focus:ring-[#99d6cc]"
                />
              </div>

              <div className="flex items-center justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setIsSettingUp(false)}
                  className="rounded-lg px-4 py-2 text-sm font-medium text-[#48615c] hover:bg-[#edf5f2]"
                >
                  Cancel
                </button>
                <button
                  disabled={actionLoading}
                  type="submit"
                  className="rounded-lg bg-[#0f766e] px-5 py-2 text-sm font-semibold text-white hover:bg-[#0b5f59] disabled:opacity-60"
                >
                  {actionLoading ? 'Activating...' : 'Confirm & Activate 2SV'}
                </button>
              </div>
            </form>
          </div>
        ) : isDisabling ? (
          /* DISABLE CONFIRMATION DIALOG */
          <form onSubmit={handleDisable2SV} className="mt-6 space-y-4">
            <div className="rounded-xl bg-amber-50 border border-amber-200 p-4 text-amber-800 text-xs leading-relaxed">
              <strong className="font-semibold">Security Warning:</strong> Disabling Two-Step Verification makes your account reliant on password authentication alone. To proceed, please confirm your credentials.
            </div>

            <label className="block text-sm font-medium text-[#172321]">
              Current Account Password
              <input
                type="password"
                value={disablePassword}
                onChange={(e) => setDisablePassword(e.target.value)}
                placeholder="Enter your password"
                className="mt-1.5 w-full rounded-lg border border-[#cddbd6] px-3 py-2 text-sm outline-none focus:border-[#0f766e] focus:ring-2 focus:ring-[#99d6cc]"
              />
            </label>

            <label className="block text-sm font-medium text-[#172321]">
              Current 6-Digit Authenticator Code (or Recovery Code)
              <input
                type="text"
                value={disableCode}
                onChange={(e) => setDisableCode(e.target.value)}
                placeholder="e.g. 123456 or xxxx-xxxx"
                className="mt-1.5 w-full rounded-lg border border-[#cddbd6] px-3 py-2 font-mono text-sm outline-none focus:border-[#0f766e] focus:ring-2 focus:ring-[#99d6cc]"
              />
            </label>

            <div className="flex items-center justify-end gap-3 pt-4 border-t border-[#e2ece9]">
              <button
                type="button"
                onClick={() => setIsDisabling(false)}
                className="rounded-lg px-4 py-2 text-sm font-medium text-[#48615c] hover:bg-[#edf5f2]"
              >
                Cancel
              </button>
              <button
                disabled={actionLoading}
                type="submit"
                className="rounded-lg bg-red-600 px-5 py-2 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-60"
              >
                {actionLoading ? 'Disabling...' : 'Confirm & Disable 2SV'}
              </button>
            </div>
          </form>
        ) : (
          /* STATUS DASHBOARD */
          <div className="mt-6 space-y-6">
            <div className="flex items-center justify-between rounded-xl border border-[#d2e0dc] bg-[#f8faf9] p-4">
              <div>
                <span className="text-xs font-semibold text-[#60736e]">Current Status</span>
                <div className="flex items-center gap-2 mt-0.5">
                  <span className={`h-2.5 w-2.5 rounded-full ${twoFactorEnabled ? 'bg-emerald-500' : 'bg-gray-400'}`} />
                  <span className="text-base font-bold text-[#172321]">
                    {twoFactorEnabled ? 'Two-Step Verification is ON' : 'Two-Step Verification is OFF'}
                  </span>
                </div>
              </div>
              <span
                className={`rounded-full px-3 py-1 text-xs font-semibold ${
                  twoFactorEnabled
                    ? 'bg-emerald-100 text-emerald-800'
                    : 'bg-gray-100 text-gray-700'
                }`}
              >
                {twoFactorEnabled ? 'Active' : 'Disabled'}
              </span>
            </div>

            {twoFactorEnabled ? (
              <div className="space-y-4">
                <div className="rounded-xl border border-[#e2ece9] p-4 text-xs text-[#48615c] leading-relaxed">
                  <p>
                    Your account requires a 6-digit code from your authenticator app each time you sign in.
                  </p>
                  <p className="mt-2 font-medium text-[#172321]">
                    Backup Recovery Codes Remaining: <span className="font-bold text-[#0f766e]">{recoveryCodesRemaining}</span>
                  </p>
                </div>
                <div className="flex justify-end pt-2">
                  <button
                    type="button"
                    onClick={() => setIsDisabling(true)}
                    className="rounded-lg border border-red-200 bg-white px-4 py-2 text-xs font-semibold text-red-600 hover:bg-red-50"
                  >
                    Disable Two-Step Verification
                  </button>
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                <p className="text-xs text-[#60736e] leading-relaxed">
                  Enhance your account security by requiring an authenticator app code during sign in. Authenticator apps (such as Google Authenticator or Apple Passwords) generate codes locally on your device without relying on email or SMS.
                </p>
                <div className="flex justify-end pt-2">
                  <button
                    type="button"
                    disabled={setupLoading}
                    onClick={handleStartSetup}
                    className="rounded-lg bg-[#0f766e] px-5 py-2.5 text-sm font-semibold text-white hover:bg-[#0b5f59] shadow-sm disabled:opacity-60"
                  >
                    {setupLoading ? 'Preparing Setup...' : 'Enable Two-Step Verification'}
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

export default SecuritySettingsModal
