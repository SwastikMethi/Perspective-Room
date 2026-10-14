import { createContext, type ReactNode, useContext } from 'react'
import { createPortal } from 'react-dom'

/** Pages render their own header actions (Saved ideas, overflow) into the shell header. */
export const HeaderSlots = createContext<{ actions: HTMLElement | null }>({ actions: null })

export function HeaderActions({ children }: { children: ReactNode }) {
  const { actions } = useContext(HeaderSlots)
  return actions ? createPortal(children, actions) : null
}
