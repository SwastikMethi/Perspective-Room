import {
  Archive,
  FlaskConical,
  MessagesSquare,
  PanelLeftClose,
  Pin,
  Plus,
  Search,
  Settings,
  Users,
} from 'lucide-react'
import type { ReactNode } from 'react'
import { Link, NavLink, useLocation } from 'react-router'
import { SidebarHistory } from '../features/workspace/SidebarHistory'
import { Logo } from './Logo'

const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform)

const navItem =
  'flex min-h-10 items-center gap-3 rounded-control px-3 text-[15px] text-text hover:bg-surface-subtle ' +
  'aria-[current=page]:bg-selection-surface aria-[current=page]:font-medium'

/** `/chats` links differ only by `?filter=`; NavLink ignores the query, so match it here. */
function ChatsLink({
  filter,
  id,
  onNavigate,
  children,
}: {
  filter: 'all' | 'pinned' | 'archived'
  id?: string
  onNavigate?: () => void
  children: ReactNode
}) {
  const { pathname, search } = useLocation()
  const current = new URLSearchParams(search).get('filter') ?? 'all'
  const active = pathname === '/chats' && current === filter
  return (
    <Link
      id={id}
      to={filter === 'all' ? '/chats' : `/chats?filter=${filter}`}
      onClick={onNavigate}
      aria-current={active ? 'page' : undefined}
      className={navItem}
    >
      {children}
    </Link>
  )
}

/** Expanded 272px navigation in doc 03 order; the history region scrolls on its own. */
export function Sidebar({
  onCollapse,
  onSearch,
  onNavigate,
}: {
  onCollapse?: () => void
  onSearch: () => void
  onNavigate?: () => void
}) {
  return (
    <div className="flex h-full flex-col bg-sidebar">
      <div className="flex items-center gap-3 px-4 pt-4 pb-3">
        <Logo />
        <span className="flex-1 truncate text-[16px] font-semibold whitespace-nowrap">
          Perspective Room
        </span>
        {onCollapse && (
          <button
            type="button"
            onClick={onCollapse}
            aria-label="Collapse sidebar"
            aria-expanded="true"
            className="grid size-10 place-items-center rounded-control text-muted hover:text-text"
          >
            <PanelLeftClose aria-hidden size={20} />
          </button>
        )}
      </div>
      <div className="px-4">
        <Link
          to="/"
          onClick={onNavigate}
          className="flex min-h-11 items-center justify-center gap-2 rounded-control bg-accent font-medium text-on-accent hover:bg-accent-hover"
        >
          <Plus aria-hidden size={20} /> New chat
        </Link>
        <button
          type="button"
          onClick={onSearch}
          className="mt-3 flex min-h-11 w-full items-center gap-3 rounded-control border border-border px-3 text-muted hover:text-text"
        >
          <Search aria-hidden size={18} /> Search chats
          <kbd className="ml-auto font-sans text-[12px]">{isMac ? '⌘K' : 'Ctrl K'}</kbd>
        </button>
      </div>
      <div className="mt-3 min-h-0 flex-1 overflow-y-auto px-2 pb-3" aria-label="Chat history">
        <ChatsLink filter="all" id="sidebar-chats" onNavigate={onNavigate}>
          <MessagesSquare aria-hidden size={18} /> All chats
        </ChatsLink>
        <ChatsLink filter="pinned" onNavigate={onNavigate}>
          <Pin aria-hidden size={18} /> Pinned
        </ChatsLink>
        <SidebarHistory onNavigate={onNavigate} />
      </div>
      <div className="border-t border-border px-2 py-2">
        <ChatsLink filter="archived" onNavigate={onNavigate}>
          <Archive aria-hidden size={18} /> Archived
        </ChatsLink>
        <NavLink to="/personalities" onClick={onNavigate} className={navItem}>
          <Users aria-hidden size={18} /> Personalities
        </NavLink>
        <NavLink to="/lab" onClick={onNavigate} className={navItem}>
          <FlaskConical aria-hidden size={18} /> Experiment Lab
        </NavLink>
        <NavLink to="/settings" onClick={onNavigate} className={navItem}>
          <Settings aria-hidden size={18} /> Settings
        </NavLink>
      </div>
    </div>
  )
}
