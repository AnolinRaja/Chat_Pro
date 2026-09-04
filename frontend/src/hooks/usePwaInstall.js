import { useEffect, useState } from 'react'

export const PWA_INSTALLED_STORAGE_KEY = 'chatpro_pwa_installed'

export function getInitialInstallState() {
  if (typeof window === 'undefined') return 'unknown'
  if (checkIsStandalone() || getStoredInstallState()) {
    return 'installed'
  }
  if (typeof navigator !== 'undefined' && 'getInstalledRelatedApps' in navigator) {
    return 'checking'
  }
  return 'not-installed'
}

let globalDeferredPrompt = null
const promptListeners = new Set()

export function getStoredInstallState() {
  if (typeof window === 'undefined') return false
  try {
    return localStorage.getItem(PWA_INSTALLED_STORAGE_KEY) === 'true'
  } catch {
    return false
  }
}

export function setStoredInstallState(isInstalled) {
  if (typeof window === 'undefined') return
  try {
    if (isInstalled) {
      localStorage.setItem(PWA_INSTALLED_STORAGE_KEY, 'true')
    } else {
      localStorage.removeItem(PWA_INSTALLED_STORAGE_KEY)
    }
  } catch {
    // Ignore storage errors
  }
}

export function checkIsStandalone() {
  if (typeof window === 'undefined') return false
  return Boolean(
    window.matchMedia?.('(display-mode: standalone)').matches ||
    window.matchMedia?.('(display-mode: window-controls-overlay)').matches ||
    window.matchMedia?.('(display-mode: minimal-ui)').matches ||
    window.navigator.standalone === true ||
    document.referrer.includes('android-app://')
  )
}

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
    // Do not capture or expose install prompt if the application is standalone or already marked as installed
    if (checkIsStandalone() || getStoredInstallState()) {
      return
    }
    event.preventDefault()
    globalDeferredPrompt = event
    notifyListeners()
  })

  // Clear prompt and record install state when app is installed
  window.addEventListener('appinstalled', () => {
    globalDeferredPrompt = null
    setStoredInstallState(true)
    notifyListeners()
  })
}

export function usePwaInstall() {
  const [deferredPrompt, setDeferredPrompt] = useState(globalDeferredPrompt)
  const [isStandalone, setIsStandalone] = useState(checkIsStandalone)
  const [installState, setInstallState] = useState(getInitialInstallState)

  useEffect(() => {
    if (typeof window === 'undefined') return undefined

    // Check navigator.getInstalledRelatedApps safely if supported
    if (typeof navigator !== 'undefined' && 'getInstalledRelatedApps' in navigator) {
      navigator.getInstalledRelatedApps()
        .then((relatedApps) => {
          if (Array.isArray(relatedApps) && relatedApps.length > 0) {
            setInstallState('installed')
            setStoredInstallState(true)
            globalDeferredPrompt = null
            setDeferredPrompt(null)
          } else {
            setInstallState((current) => (current === 'installed' ? 'installed' : 'not-installed'))
          }
        })
        .catch(() => {
          setInstallState((current) =>
            current === 'installed' ? 'installed' : 'unknown'
          )
        })
    }

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
        setInstallState('installed')
        setStoredInstallState(true)
        globalDeferredPrompt = null
        setDeferredPrompt(null)
      } else {
        setIsStandalone(checkIsStandalone())
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
      if (choiceResult && choiceResult.outcome === 'accepted') {
        globalDeferredPrompt = null
        setDeferredPrompt(null)
        setInstallState('installed')
        setStoredInstallState(true)
        notifyListeners()
        return true
      }
      return false
    } catch {
      return false
    }
  }

  const isInstalled = installState === 'installed' || isStandalone
  const isInstallable = Boolean(
    deferredPrompt &&
    !isStandalone &&
    installState === 'not-installed'
  )

  return {
    isInstallable,
    isStandalone,
    isInstalled,
    installState,
    installPwa,
  }
}
