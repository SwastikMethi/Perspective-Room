import { useSyncExternalStore } from 'react'

export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (onChange) => {
      if (!window.matchMedia) return () => {}
      const mql = window.matchMedia(query)
      mql.addEventListener('change', onChange)
      return () => mql.removeEventListener('change', onChange)
    },
    () => (window.matchMedia ? window.matchMedia(query).matches : false),
    () => false,
  )
}

/** Below 900px the fixed sidebar becomes a menu button + overlay drawer (doc 03). */
export const NARROW_QUERY = '(max-width: 899.98px)'
