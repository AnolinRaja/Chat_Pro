import { useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import AuthCard from '../components/AuthCard.jsx'
import FormMessage from '../components/FormMessage.jsx'
import { useAuth } from '../context/useAuth.js'
import { validateRegistration } from '../utils/validation.js'

function RegisterPage() {
  const { user, register } = useAuth()
  const navigate = useNavigate()
  const [form, setForm] = useState({ name: '', email: '', password: '' })
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

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
      setSuccess('Account created. You can sign in now.')
      setTimeout(() => navigate('/login', { replace: true }), 700)
    } catch (submitError) {
      setError(submitError.message)
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <section className="mx-auto flex min-h-[calc(100vh-73px)] max-w-xl items-center px-5 py-12 sm:px-8">
      <AuthCard eyebrow="Start a new chapter" title="Create your ChatPRO account" description="A simple home for your everyday conversations.">
        <form className="mt-7 space-y-5" onSubmit={handleSubmit} noValidate>
          <FormMessage>{error || success}</FormMessage>
          <label className="block text-sm font-medium">Name<input name="name" type="text" value={form.name} onChange={updateField} autoComplete="name" placeholder="Your name" className="mt-2 w-full rounded-lg border border-[#cddbd6] px-3 py-3 outline-none focus:border-[#0f766e] focus:ring-2 focus:ring-[#99d6cc]" /></label>
          <label className="block text-sm font-medium">Email<input name="email" type="email" value={form.email} onChange={updateField} autoComplete="email" placeholder="you@example.com" className="mt-2 w-full rounded-lg border border-[#cddbd6] px-3 py-3 outline-none focus:border-[#0f766e] focus:ring-2 focus:ring-[#99d6cc]" /></label>
          <label className="block text-sm font-medium">Password<input name="password" type="password" value={form.password} onChange={updateField} autoComplete="new-password" placeholder="At least 8 characters" className="mt-2 w-full rounded-lg border border-[#cddbd6] px-3 py-3 outline-none focus:border-[#0f766e] focus:ring-2 focus:ring-[#99d6cc]" /></label>
          <button disabled={isSubmitting || Boolean(success)} type="submit" className="w-full rounded-lg bg-[#172321] px-4 py-3 font-semibold text-white hover:bg-[#2d413c] disabled:cursor-not-allowed disabled:opacity-60">{isSubmitting ? 'Creating account...' : 'Create account'}</button>
        </form>
        <p className="mt-6 text-center text-sm text-[#60736e]">Already have an account? <Link to="/login" className="font-semibold text-[#0f766e] hover:underline">Sign in</Link></p>
      </AuthCard>
    </section>
  )
}

export default RegisterPage
