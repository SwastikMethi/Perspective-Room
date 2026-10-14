import {
  Archive,
  FlaskConical,
  FolderPlus,
  MessagesSquare,
  PanelLeftClose,
  Pin,
  Plus,
  Search,
  Settings,
  Users,
} from 'lucide-react'
import type { ReactNode } from 'react'
import { Link, NavLink } from 'react-router'
import { Logo } from './Logo'

const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform)

const navItem =
  'flex min-h-10 items-center gap-3 rounded-control px-3 text-[15px] text-text hover:bg-surface-subtle ' +
  'aria-[current=page]:bg-selection-surface aria-[current=page]:font-medium'

export function SidebarSection({
  title,
  action,
  children,
}: {
  title: string
  action?: ReactNode
  children?: ReactNode
}) {
  return (
    <section aria-label={title} className="mt-5">
      <div className="flex items-center justify-between px-3 pb-1">
        <h2 className="text-[12px] font-medium tracking-[0.12em] text-muted uppercase">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  )
}

/** Expanded 272px navigation. History lists plug in via `history` (doc 14 order). */
export function Sidebar({
  onCollapse,
  onSearch,
  onNavigate,
  history,
  folderAction,
}: {
  onCollapse?: () => void
  onSearch: () => void
  onNavigate?: () => void
  history?: ReactNode
  folderAction?: ReactNode
}) {
  return (
    <div className="flex h-full flex-col bg-sidebar">
      <div className="flex items-center gap-3 px-4 pt-4 pb-3">
        <Logo />
        <span className="flex-1 truncate text-[16px] font-semibold whitespace-nowrap">Perspective Room</span>
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
          <kbd className="ml-auto text-[12px]">{isMac ? '⌘K' : 'Ctrl K'}</kbd>
        </button>
      </div>
      <div className="mt-3 min-h-0 flex-1 overflow-y-auto px-2" aria-label="Chat history">
        <NavLink to="/chats" end onClick={onNavigate} className={navItem}>
          <MessagesSquare aria-hidden size={18} /> All chats
        </NavLink>
        <NavLink to="/chats?filter=pinned" onClick={onNavigate} className={navItem}>
          <Pin aria-hidden size={18} /> Pinned
        </NavLink>
        <SidebarSection
          title="Folders"
          action={
            folderAction ?? (
              <span aria-hidden className="grid size-8 place-items-center text-muted">
                <FolderPlus size={16} />
              </span>
            )
          }
        />
        {history}
      </div>
      <div className="border-t border-border px-2 py-2">
        <NavLink to="/chats?filter=archived" onClick={onNavigate} className={navItem}>
          <Archive aria-hidden size={18} /> Archived
        </NavLink>
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
