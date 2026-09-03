import { useEffect, useState } from 'react'

let globalDeferredPrompt = null
const promptListeners = new Set()

function notifyListeners() {
  promptListeners.forEach((listener) => {
    try {
      listener(globalDeferredPrompt)
    } catch {
      // Ignore listener error
    }
  })
}

if (typeof window !== 'undefined') {
  // Capture beforeinstallprompt immediately upon module evaluation
  window.addEventListener('beforeinstallprompt', (event) => {
    event.preventDefault()
    globalDeferredPrompt = event
    notifyListeners()
  })

  // Clear prompt when app is installed
  window.addEventListener('appinstalled', () => {
    globalDeferredPrompt = null
    notifyListeners()
  })
}

function checkIsStandalone() {
  if (typeof window === 'undefined') return false
  return (
    window.matchMedia?.('(display-mode: standalone)').matches ||
    window.navigator.standalone === true ||
    document.referrer.includes('android-app://')
  )
}

export function usePwaInstall() {
  const [deferredPrompt, setDeferredPrompt] = useState(globalDeferredPrompt)
  const [isStandalone, setIsStandalone] = useState(checkIsStandalone)

  useEffect(() => {
    if (typeof window === 'undefined') return undefined

    // Subscribe to module-level prompt updates
    const handlePromptChange = (updatedPrompt) => {
      setDeferredPrompt(updatedPrompt)
    }
    promptListeners.add(handlePromptChange)

    // Monitor display-mode changes
    const mediaQuery = window.matchMedia?.('(display-mode: standalone)')
    const handleDisplayChange = (e) => {
      if (e.matches) {
        setIsStandalone(true)
        globalDeferredPrompt = null
        setDeferredPrompt(null)
      } else {
        setIsStandalone(false)
      }
    }

    if (mediaQuery?.addEventListener) {
      mediaQuery.addEventListener('change', handleDisplayChange)
    } else if (mediaQuery?.addListener) {
      mediaQuery.addListener(handleDisplayChange)
    }

    return () => {
      promptListeners.delete(handlePromptChange)
      if (mediaQuery?.removeEventListener) {
        mediaQuery.removeEventListener('change', handleDisplayChange)
      } else if (mediaQuery?.removeListener) {
        mediaQuery.removeListener(handleDisplayChange)
      }
    }
  }, [])

  // Native browser PWA install prompt
  const installPwa = async () => {
    const promptToUse = deferredPrompt || globalDeferredPrompt
    if (!promptToUse) return false

    try {
      await promptToUse.prompt()
      const choiceResult = await promptToUse.userChoice
      if (choiceResult.outcome === 'accepted') {
        globalDeferredPrompt = null
        setDeferredPrompt(null)
        notifyListeners()
        return true
      }
      return false
    } catch {
      return false
    }
  }

  const isInstallable = Boolean(deferredPrompt && !isStandalone)

  return {
    isInstallable,
    isStandalone,
    installPwa,
  }
}
