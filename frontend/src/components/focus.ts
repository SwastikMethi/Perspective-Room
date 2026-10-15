// Focus restoration for controlled Radix dialogs/drawers (doc 03: menus and dialogs return focus).
// Radix restores focus only to a Dialog.Trigger; ours open from menus, shortcuts and stores.
import { useLayoutEffect, useRef } from 'react'

/** The element focus should return to: a menu item resolves to its menu's trigger. */
export function openerOf(el: Element | null): HTMLElement | null {
  if (!(el instanceof HTMLElement) || el === document.body) return null
  const menu = el.closest('[role="menu"]')
  if (menu?.id) {
    const trigger = document.querySelector<HTMLElement>(`[aria-controls="${CSS.escape(menu.id)}"]`)
    if (trigger) return trigger
  }
  return el
}

/** Remember the opener when `open` turns true; pass the result to onCloseAutoFocus. */
export function useReturnFocus(open: boolean) {
  const opener = useRef<HTMLElement | null>(null)
  useLayoutEffect(() => {
    if (open) opener.current = openerOf(document.activeElement)
  }, [open])
  return (e: Event) => {
    const el = opener.current
    if (el?.isConnected) {
      e.preventDefault()
      el.focus()
    }
  }
}
