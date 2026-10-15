import { useQueryClient } from '@tanstack/react-query'
import { ChevronDown, ChevronRight, Folder, FolderPlus, MoreHorizontal } from 'lucide-react'
import { DropdownMenu } from 'radix-ui'
import { Link, useMatch, useNavigate } from 'react-router'
import type { Schemas } from '../../api/client'
import { historyItems, useFolders, useHistory } from '../../api/queries'
import { useUi } from '../../stores/ui'
import { createFolder, deleteFolder, renameFolder } from './actions'
import { ChatRow, MenuItem, menuContent } from './ChatRow'

export function SectionHeading({
  id,
  title,
  action,
}: {
  id: string
  title: string
  action?: React.ReactNode
}) {
  return (
    <div className="flex items-center justify-between px-3 pt-5 pb-1">
      <h2 id={id} tabIndex={-1} className="text-[13px] font-medium text-muted">
        {title}
      </h2>
      {action}
    </div>
  )
}

function LoadMore({ query }: { query: ReturnType<typeof useHistory> }) {
  if (!query.hasNextPage) return null
  return (
    <button
      type="button"
      onClick={() => void query.fetchNextPage()}
      disabled={query.isFetchingNextPage}
      className="ml-3 min-h-9 rounded-control px-2 text-[13px] text-muted underline-offset-2 hover:text-text hover:underline"
    >
      {query.isFetchingNextPage ? 'Loading…' : 'Load more'}
    </button>
  )
}

function FolderChildren({
  folder,
  onNavigate,
}: {
  folder: Schemas['Folder']
  onNavigate?: () => void
}) {
  const q = useHistory({ folder_id: folder.id, archive: 'active' })
  const chats = historyItems(q.data)
  if (q.isPending) return <p className="py-1 pl-10 text-[13px] text-muted">Loading…</p>
  if (q.isError) return <p className="py-1 pl-10 text-[13px] text-danger">Chats could not load.</p>
  if (chats.length === 0)
    return (
      <p className="py-1 pl-10 text-[13px] text-muted">
        No chats yet ·{' '}
        <Link to={`/?folder=${folder.id}`} onClick={onNavigate} className="underline">
          New chat
        </Link>
      </p>
    )
  return (
    <div role="group" aria-label={`Chats in ${folder.name}`}>
      {chats.map((c) => (
        <ChatRow key={c.id} chat={c} indent onNavigate={onNavigate} />
      ))}
      <LoadMore query={q} />
    </div>
  )
}

function FolderRow({ folder, onNavigate }: { folder: Schemas['Folder']; onNavigate?: () => void }) {
  const open = useUi((s) => s.openFolderIds.includes(folder.id))
  const toggle = useUi((s) => s.toggleFolder)
  const match = useMatch('/folders/:folderId')
  const qc = useQueryClient()
  const navigate = useNavigate()
  const active = match?.params.folderId === folder.id
  return (
    <div>
      <div
        className={
          'group flex min-h-10 items-center rounded-control pr-1 ' +
          (active ? 'bg-selection-surface' : 'hover:bg-surface-subtle')
        }
      >
        <button
          type="button"
          onClick={() => toggle(folder.id)}
          aria-expanded={open}
          aria-label={`${open ? 'Close' : 'Open'} ${folder.name}`}
          className="grid size-9 shrink-0 place-items-center rounded-control text-muted hover:text-text"
        >
          {open ? <ChevronDown aria-hidden size={16} /> : <ChevronRight aria-hidden size={16} />}
        </button>
        <Link
          to={`/folders/${folder.id}`}
          onClick={onNavigate}
          aria-current={active ? 'page' : undefined}
          className="flex min-h-10 min-w-0 flex-1 items-center gap-2 text-[15px]"
        >
          <Folder aria-hidden size={16} className="shrink-0 text-muted" />
          <span className="truncate" title={folder.name}>
            {folder.name}
          </span>
          <span className="ml-auto shrink-0 pr-1 text-[12px] text-muted">
            {folder.chat_count}
            <span className="sr-only"> chats</span>
          </span>
        </Link>
        <DropdownMenu.Root>
          <DropdownMenu.Trigger asChild>
            <button
              type="button"
              aria-label={`Actions for folder ${folder.name}`}
              className="grid size-9 shrink-0 place-items-center rounded-control text-muted opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 hover:text-text focus-visible:opacity-100 data-[state=open]:opacity-100 [@media(pointer:coarse)]:opacity-100"
            >
              <MoreHorizontal aria-hidden size={18} />
            </button>
          </DropdownMenu.Trigger>
          <DropdownMenu.Portal>
            <DropdownMenu.Content align="end" sideOffset={4} className={menuContent}>
              <MenuItem
                onSelect={() => {
                  onNavigate?.()
                  navigate(`/?folder=${folder.id}`)
                }}
              >
                New chat here
              </MenuItem>
              <MenuItem onSelect={() => void renameFolder(qc, folder)}>Rename</MenuItem>
              <MenuItem
                danger
                onSelect={async () => {
                  if ((await deleteFolder(qc, folder)) && active) navigate('/chats')
                }}
              >
                Delete folder…
              </MenuItem>
            </DropdownMenu.Content>
          </DropdownMenu.Portal>
        </DropdownMenu.Root>
      </div>
      {open && <FolderChildren folder={folder} onNavigate={onNavigate} />}
    </div>
  )
}

/** Folders and Recent (doc 03 sidebar order). Lists are paginated and never load transcripts. */
export function SidebarHistory({ onNavigate }: { onNavigate?: () => void }) {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const folders = useFolders()
  const recent = useHistory({ pinned: false, archive: 'active' })
  const chats = historyItems(recent.data)
  return (
    <>
      <section aria-labelledby="sidebar-folders">
        <SectionHeading
          id="sidebar-folders"
          title="Folders"
          action={
            <button
              type="button"
              aria-label="New folder"
              onClick={async () => {
                const f = await createFolder(qc)
                if (f) {
                  onNavigate?.()
                  navigate(`/folders/${f.id}`)
                }
              }}
              className="grid size-9 place-items-center rounded-control text-muted hover:bg-surface-subtle hover:text-text"
            >
              <FolderPlus aria-hidden size={17} />
            </button>
          }
        />
        {folders.isError && <p className="px-3 text-[13px] text-danger">Folders could not load.</p>}
        {folders.data?.length === 0 && (
          <p className="px-3 text-[13px] text-muted">No folders yet.</p>
        )}
        {folders.data?.map((f) => (
          <FolderRow key={f.id} folder={f} onNavigate={onNavigate} />
        ))}
      </section>
      <section aria-labelledby="sidebar-recent">
        <SectionHeading id="sidebar-recent" title="Recent" />
        {recent.isPending && <p className="px-3 text-[13px] text-muted">Loading…</p>}
        {recent.isError && <p className="px-3 text-[13px] text-danger">Chats could not load.</p>}
        {recent.isSuccess && chats.length === 0 && (
          <p className="px-3 text-[13px] text-muted">Your chats will appear here.</p>
        )}
        {chats.map((c) => (
          <ChatRow key={c.id} chat={c} onNavigate={onNavigate} />
        ))}
        <LoadMore query={recent} />
      </section>
    </>
  )
}
