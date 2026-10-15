import { useQueryClient } from '@tanstack/react-query'
import { Loader2, MessageSquareText, MoreHorizontal, Pin } from 'lucide-react'
import { DropdownMenu } from 'radix-ui'
import type { ReactNode } from 'react'
import { Link, useMatch, useNavigate } from 'react-router'
import { useFolders } from '../../api/queries'
import {
  type ChatSummary,
  deleteChat,
  duplicateChat,
  exportChat,
  moveChat,
  organize,
  renameChat,
  setArchived,
} from './actions'

export const menuContent =
  'z-50 min-w-52 rounded-card border border-border bg-surface p-1 text-[15px] text-text shadow-xl'
export const menuItem =
  'flex min-h-10 cursor-pointer items-center gap-2 rounded-control px-3 outline-none select-none ' +
  'data-[highlighted]:bg-surface-subtle data-[disabled]:cursor-default data-[disabled]:opacity-60'

export function MenuItem({
  onSelect,
  children,
  danger,
  disabled,
}: {
  onSelect: () => void
  children: ReactNode
  danger?: boolean
  disabled?: boolean
}) {
  return (
    <DropdownMenu.Item
      className={menuItem + (danger ? ' text-danger' : '')}
      onSelect={onSelect}
      disabled={disabled}
    >
      {children}
    </DropdownMenu.Item>
  )
}

/** Every chat action from doc 14, shared by sidebar rows, list pages and the room header. */
export function ChatMenuItems({ chat, onDeleted }: { chat: ChatSummary; onDeleted?: () => void }) {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const folders = useFolders()
  const running = Boolean(chat.active_run_id)
  return (
    <>
      <MenuItem onSelect={() => navigate(`/rooms/${chat.id}`)}>Open</MenuItem>
      <MenuItem onSelect={() => void renameChat(qc, chat)}>Rename</MenuItem>
      {!chat.is_archived && (
        <>
          <MenuItem onSelect={() => void organize(qc, chat, { is_pinned: !chat.is_pinned })}>
            {chat.is_pinned ? 'Unpin' : 'Pin'}
          </MenuItem>
          <MenuItem onSelect={() => void moveChat(qc, chat, folders.data ?? [])}>
            Move to folder…
          </MenuItem>
          <MenuItem
            onSelect={async () => {
              const id = await duplicateChat(qc, chat)
              if (id) navigate(`/rooms/${id}`)
            }}
          >
            Duplicate
          </MenuItem>
        </>
      )}
      <MenuItem onSelect={() => void exportChat(chat, 'markdown')}>Export as Markdown</MenuItem>
      <MenuItem onSelect={() => void exportChat(chat, 'json')}>Export as JSON</MenuItem>
      <DropdownMenu.Separator className="my-1 h-px bg-border" />
      {chat.is_archived ? (
        <MenuItem onSelect={() => void setArchived(qc, chat, false)}>Restore</MenuItem>
      ) : (
        <MenuItem onSelect={() => void setArchived(qc, chat, true)}>
          {running ? 'Archive… (stops the reply)' : 'Archive'}
        </MenuItem>
      )}
      <MenuItem
        danger
        onSelect={async () => {
          if (await deleteChat(qc, chat)) onDeleted?.()
        }}
      >
        Delete…
      </MenuItem>
    </>
  )
}

export function ChatMenu({
  chat,
  onDeleted,
  trigger,
}: {
  chat: ChatSummary
  onDeleted?: () => void
  trigger?: ReactNode
}) {
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        {trigger ?? (
          <button
            type="button"
            aria-label={`Actions for ${chat.title}`}
            className="grid size-9 shrink-0 place-items-center rounded-control text-muted opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 hover:text-text focus-visible:opacity-100 data-[state=open]:opacity-100 [@media(pointer:coarse)]:opacity-100"
          >
            <MoreHorizontal aria-hidden size={18} />
          </button>
        )}
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content align="end" sideOffset={4} className={menuContent}>
          <ChatMenuItems chat={chat} onDeleted={onDeleted} />
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  )
}

/** One history row: active state, truncated title with its full accessible name, a non-color
 * working indicator, and an overflow menu reachable by hover, keyboard focus and touch. */
export function ChatRow({
  chat,
  onNavigate,
  indent = false,
}: {
  chat: ChatSummary
  onNavigate?: () => void
  indent?: boolean
}) {
  const match = useMatch('/rooms/:id')
  const navigate = useNavigate()
  const active = match?.params.id === chat.id
  return (
    <div
      className={
        'group relative flex min-h-10 items-center rounded-control pr-1 ' +
        (active
          ? 'bg-selection-surface before:absolute before:inset-y-1 before:left-0 before:w-[3px] before:rounded-full before:bg-selection-border'
          : 'hover:bg-surface-subtle')
      }
    >
      <Link
        to={`/rooms/${chat.id}`}
        onClick={onNavigate}
        aria-current={active ? 'page' : undefined}
        title={chat.title}
        className={
          'flex min-h-10 min-w-0 flex-1 items-center gap-3 rounded-control py-1 text-[15px] ' +
          (indent ? 'pl-8' : 'pl-3')
        }
      >
        <MessageSquareText aria-hidden size={16} className="shrink-0 text-muted" />
        <span className="min-w-0 flex-1 truncate">{chat.title}</span>
        {chat.is_pinned && <Pin aria-label="Pinned" size={14} className="shrink-0 text-muted" />}
        {chat.active_run_id && (
          <span className="flex shrink-0 items-center gap-1 text-[12px] text-muted">
            <Loader2 aria-hidden size={14} className="animate-spin motion-reduce:animate-none" />
            <span className="sr-only">Working</span>
          </span>
        )}
      </Link>
      <ChatMenu
        chat={chat}
        onDeleted={() => {
          if (active) navigate('/')
        }}
      />
    </div>
  )
}
