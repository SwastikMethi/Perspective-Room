import {
  FlaskConical,
  Folder,
  Menu,
  MessagesSquare,
  Plus,
  Search,
  Settings,
  Users,
  X,
} from 'lucide-react'
import { Dialog, Tooltip } from 'radix-ui'
import { type ReactNode, useEffect, useState } from 'react'
import { Link, NavLink, Outlet } from 'react-router'
import { SearchDialog } from '../features/search/SearchDialog'
import { useUi } from '../stores/ui'
import { DialogHost, NoticeHost } from './Dialogs'
import { useReturnFocus } from './focus'
import { HeaderSlots } from './HeaderActions'
import { Logo } from './Logo'
import { ReadinessBanner } from './ReadinessBanner'
import { Sidebar } from './Sidebar'
import { ThemeSwitch } from './ThemeSwitch'
import { NARROW_QUERY, useMediaQuery } from './useMediaQuery'

const railButton =
  'grid size-11 place-items-center rounded-control text-muted hover:bg-surface-subtle hover:text-text ' +
  'aria-[current=page]:bg-selection-surface aria-[current=page]:text-text'

function RailTip({ label, children }: { label: string; children: ReactNode }) {
  return (
    <Tooltip.Root>
      <Tooltip.Trigger asChild>{children}</Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Content
          side="right"
          sideOffset={8}
          className="z-50 rounded-control border border-border bg-surface px-2 py-1 text-[13px] text-text shadow"
        >
          {label}
        </Tooltip.Content>
      </Tooltip.Portal>
    </Tooltip.Root>
  )
}

/** Collapsed 64px rail: every destination stays reachable with labeled icons. */
function Rail({
  onExpand,
  onSearch,
}: {
  onExpand: (section?: 'chats' | 'folders') => void
  onSearch: () => void
}) {
  return (
    <div className="flex h-full flex-col items-center gap-2 bg-sidebar py-3">
      <RailTip label="Expand sidebar">
        <button
          type="button"
          onClick={() => onExpand()}
          aria-label="Expand sidebar"
          aria-expanded="false"
          className={railButton}
        >
          <Logo size={30} />
        </button>
      </RailTip>
      <RailTip label="New chat">
        <Link
          to="/"
          aria-label="New chat"
          className="mt-2 grid size-12 place-items-center rounded-card bg-accent text-on-accent hover:bg-accent-hover"
        >
          <Plus aria-hidden size={24} />
        </Link>
      </RailTip>
      <RailTip label="Search chats">
        <button type="button" onClick={onSearch} aria-label="Search chats" className={railButton}>
          <Search aria-hidden size={20} />
        </button>
      </RailTip>
      <RailTip label="Chats">
        <button
          type="button"
          onClick={() => onExpand('chats')}
          aria-label="Chats"
          className={railButton}
        >
          <MessagesSquare aria-hidden size={20} />
        </button>
      </RailTip>
      <RailTip label="Folders">
        <button
          type="button"
          onClick={() => onExpand('folders')}
          aria-label="Folders"
          className={railButton}
        >
          <Folder aria-hidden size={20} />
        </button>
      </RailTip>
      <RailTip label="Personalities">
        <NavLink to="/personalities" aria-label="Personalities" className={railButton}>
          <Users aria-hidden size={20} />
        </NavLink>
      </RailTip>
      <RailTip label="Experiment Lab">
        <NavLink to="/lab" aria-label="Experiment Lab" className={railButton}>
          <FlaskConical aria-hidden size={20} />
        </NavLink>
      </RailTip>
      <div className="flex-1" />
      <RailTip label="Settings">
        <NavLink to="/settings" aria-label="Settings" className={railButton}>
          <Settings aria-hidden size={20} />
        </NavLink>
      </RailTip>
    </div>
  )
}

export function AppShell() {
  const expanded = useUi((s) => s.sidebarExpanded)
  const setExpanded = useUi((s) => s.setSidebarExpanded)
  const drawerOpen = useUi((s) => s.mobileDrawerOpen)
  const setDrawerOpen = useUi((s) => s.setMobileDrawerOpen)
  const narrow = useMediaQuery(NARROW_QUERY)
  const [searchOpen, setSearchOpen] = useState(false)
  const [actionsEl, setActionsEl] = useState<HTMLElement | null>(null)
  const returnFocus = useReturnFocus(drawerOpen)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setSearchOpen(true)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const closeDrawer = () => setDrawerOpen(false)
  const expandTo = (section?: 'chats' | 'folders') => {
    setExpanded(true)
    if (section)
      requestAnimationFrame(() => {
        const el = document.getElementById(`sidebar-${section}`)
        el?.scrollIntoView({ block: 'nearest' })
        el?.focus()
      })
  }
  const openSearch = () => {
    setDrawerOpen(false)
    setSearchOpen(true)
  }

  return (
    <Tooltip.Provider delayDuration={300}>
      <HeaderSlots.Provider value={{ actions: actionsEl }}>
        <div className="flex h-dvh overflow-hidden bg-canvas text-text">
          <a href="#main" className="skip-link">
            Skip to content
          </a>
          {!narrow && (
            <nav
              aria-label="Primary"
              className="shrink-0 border-r border-border transition-[width] duration-[var(--motion-duration)]"
              style={{
                width: expanded
                  ? 'var(--layout-sidebar-expanded)'
                  : 'var(--layout-sidebar-collapsed)',
              }}
            >
              {expanded ? (
                <Sidebar onCollapse={() => setExpanded(false)} onSearch={openSearch} />
              ) : (
                <Rail onExpand={expandTo} onSearch={openSearch} />
              )}
            </nav>
          )}
          {narrow && (
            <Dialog.Root open={drawerOpen} onOpenChange={setDrawerOpen}>
              <Dialog.Portal>
                <Dialog.Overlay className="fixed inset-0 z-40 bg-black/50" />
                <Dialog.Content
                  onCloseAutoFocus={returnFocus}
                  aria-label="Navigation"
                  className="fixed inset-y-0 left-0 z-50 w-[min(var(--layout-mobile-drawer-max),88vw)] border-r border-border shadow-xl"
                >
                  <Dialog.Title className="sr-only">Navigation</Dialog.Title>
                  <Dialog.Description className="sr-only">
                    Chats, folders and app sections
                  </Dialog.Description>
                  <Dialog.Close
                    aria-label="Close navigation"
                    className="absolute top-4 right-3 grid size-10 place-items-center rounded-control text-muted hover:text-text"
                  >
                    <X aria-hidden size={20} />
                  </Dialog.Close>
                  <nav aria-label="Primary" className="h-full">
                    <Sidebar onSearch={openSearch} onNavigate={closeDrawer} />
                  </nav>
                </Dialog.Content>
              </Dialog.Portal>
            </Dialog.Root>
          )}
          <div className="flex min-w-0 flex-1 flex-col">
            <header className="flex h-[var(--layout-header-height)] shrink-0 items-center gap-3 border-b border-border px-4 sm:px-6">
              {narrow && (
                <button
                  type="button"
                  onClick={() => setDrawerOpen(true)}
                  aria-label="Open navigation"
                  aria-expanded={drawerOpen}
                  className="grid size-11 place-items-center rounded-control text-muted hover:text-text"
                >
                  <Menu aria-hidden size={22} />
                </button>
              )}
              <span className="flex min-w-0 flex-1 items-center gap-2 truncate text-[19px] font-semibold sm:text-[22px]">
                <span className="sm:hidden" aria-hidden>
                  <Logo size={26} />
                </span>
                <span className="max-sm:sr-only">Perspective Room</span>
              </span>
              <div ref={setActionsEl} className="flex items-center gap-3" />
              <ThemeSwitch />
            </header>
            <ReadinessBanner />
            <main id="main" tabIndex={-1} className="relative min-h-0 flex-1 overflow-y-auto">
              <Outlet />
            </main>
          </div>
        </div>
        <SearchDialog open={searchOpen} onOpenChange={setSearchOpen} />
        <DialogHost />
        <NoticeHost />
      </HeaderSlots.Provider>
    </Tooltip.Provider>
  )
}
