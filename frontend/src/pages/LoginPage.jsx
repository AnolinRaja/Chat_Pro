import { useState } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import AuthCard from '../components/AuthCard.jsx'
import FormMessage from '../components/FormMessage.jsx'
import { useAuth } from '../context/useAuth.js'
import { validateLogin } from '../utils/validation.js'

function LoginPage() {
  const { user, login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [form, setForm] = useState({ email: '', password: '' })
  const [error, setError] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  if (user) return <Navigate to="/chat" replace />

  const updateField = (event) => setForm({ ...form, [event.target.name]: event.target.value })

  const handleSubmit = async (event) => {
    event.preventDefault()
    const validationError = validateLogin(form)
    if (validationError) return setError(validationError)
    setError('')
    setIsSubmitting(true)
    try {
      await login({ email: form.email, password: form.password })
      navigate(location.state?.from?.pathname || '/chat', { replace: true })
    } catch (submitError) {
      setError(submitError.message)
    } finally {
      setIsSubmitting(false)
    }
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
          <label className="block text-sm font-medium">Email<input name="email" type="email" value={form.email} onChange={updateField} autoComplete="email" placeholder="you@example.com" className="mt-2 w-full rounded-lg border border-[#cddbd6] px-3 py-3 outline-none focus:border-[#0f766e] focus:ring-2 focus:ring-[#99d6cc]" /></label>
          <label className="block text-sm font-medium">Password<input name="password" type="password" value={form.password} onChange={updateField} autoComplete="current-password" placeholder="Enter your password" className="mt-2 w-full rounded-lg border border-[#cddbd6] px-3 py-3 outline-none focus:border-[#0f766e] focus:ring-2 focus:ring-[#99d6cc]" /></label>
          <button disabled={isSubmitting} type="submit" className="w-full rounded-lg bg-[#0f766e] px-4 py-3 font-semibold text-white hover:bg-[#0b5f59] disabled:cursor-not-allowed disabled:opacity-60">{isSubmitting ? 'Signing in...' : 'Sign in'}</button>
        </form>
        <p className="mt-6 text-center text-sm text-[#60736e]">New to ChatPRO? <Link to="/register" className="font-semibold text-[#0f766e] hover:underline">Create an account</Link></p>
      </AuthCard>
    </section>
  )
}

export default LoginPage
