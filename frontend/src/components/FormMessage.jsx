function FormMessage({ children }) {
  if (!children) return null
  return <p role="alert" className="rounded-xl bg-red-500/10 border border-red-500/20 px-3.5 py-3 text-sm text-red-600 font-medium">{children}</p>
}

export default FormMessage
