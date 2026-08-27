function FormMessage({ children }) {
  if (!children) return null
  return <p role="alert" className="rounded-lg bg-[#fff0ee] px-3 py-3 text-sm text-[#a63d32]">{children}</p>
}

export default FormMessage
