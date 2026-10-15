import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Folder, MoreHorizontal, Plus } from 'lucide-react'
import { DropdownMenu } from 'radix-ui'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { ApiError, api, unwrap } from '../../api/client'
import { keys } from '../../api/queries'
import { deleteFolder, renameFolder } from '../workspace/actions'
import { ChatList } from '../workspace/ChatList'
import { MenuItem, menuContent } from '../workspace/ChatRow'

export function FolderPage() {
  const { folderId = '' } = useParams()
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [showArchived, setShowArchived] = useState(false)
  const folder = useQuery({
    queryKey: keys.folder(folderId),
    queryFn: () =>
      unwrap(api.GET('/api/v1/folders/{folder_id}', { params: { path: { folder_id: folderId } } })),
  })
  const shell = 'mx-auto max-w-[var(--layout-workspace-max)] px-4 py-8 sm:px-6 lg:px-12'
  if (folder.isError) {
    const gone = folder.error instanceof ApiError && folder.error.status === 404
    return (
      <section className={shell}>
        <h1 className="text-[length:var(--text-title)] font-semibold">
          {gone ? 'This folder no longer exists' : 'This folder could not load'}
        </h1>
        <p className="mt-2 text-muted">
          {gone ? 'It may have been deleted; its chats were kept. ' : `${folder.error.message} `}
          <Link to="/chats" className="underline">
            Open all chats
          </Link>
        </p>
      </section>
    )
  }
  const f = folder.data
  return (
    <section className={shell}>
      <nav aria-label="Breadcrumb" className="text-[13px] text-muted">
        <Link to="/chats" className="hover:underline">
          Chats
        </Link>{' '}
        / <span aria-current="page">{f?.name ?? '…'}</span>
      </nav>
      <div className="mt-1 mb-6 flex flex-wrap items-center gap-3">
        <h1 className="flex min-w-0 flex-1 items-center gap-3 text-[length:var(--text-title)] leading-tight font-semibold">
          <Folder aria-hidden className="shrink-0 text-muted" />
          <span className="break-words">{f?.name ?? ' '}</span>
        </h1>
        <Link
          to={`/?folder=${folderId}`}
          className="inline-flex min-h-10 items-center gap-2 rounded-control bg-accent px-4 font-medium text-on-accent hover:bg-accent-hover"
        >
          <Plus aria-hidden size={18} /> New chat here
        </Link>
        {f && (
          <DropdownMenu.Root>
            <DropdownMenu.Trigger
              aria-label={`Actions for folder ${f.name}`}
              className="grid size-10 place-items-center rounded-control border border-border text-muted hover:text-text"
            >
              <MoreHorizontal aria-hidden size={18} />
            </DropdownMenu.Trigger>
            <DropdownMenu.Portal>
              <DropdownMenu.Content align="end" sideOffset={4} className={menuContent}>
                <MenuItem
                  onSelect={async () => {
                    await renameFolder(qc, f)
                    await qc.invalidateQueries({ queryKey: keys.folder(folderId) })
                  }}
                >
                  Rename
                </MenuItem>
                <MenuItem
                  danger
                  onSelect={async () => {
                    if (await deleteFolder(qc, f)) navigate('/chats')
                  }}
                >
                  Delete folder…
                </MenuItem>
              </DropdownMenu.Content>
            </DropdownMenu.Portal>
          </DropdownMenu.Root>
        )}
      </div>
      <ChatList
        params={{ folder_id: folderId, archive: 'active' }}
        empty={
          <div className="rounded-card border border-dashed border-border p-8 text-center">
            <p className="font-medium">No chats yet</p>
            <Link
              to={`/?folder=${folderId}`}
              className="mt-3 inline-flex min-h-10 items-center gap-2 rounded-control bg-accent px-4 font-medium text-on-accent"
            >
              <Plus aria-hidden size={18} /> New chat
            </Link>
          </div>
        }
      />
      {f && f.archived_chat_count > 0 && (
        <div className="mt-8">
          <button
            type="button"
            aria-expanded={showArchived}
            onClick={() => setShowArchived((v) => !v)}
            className="min-h-10 text-muted underline-offset-2 hover:text-text hover:underline"
          >
            {showArchived ? 'Hide' : 'Show'} archived chats in this folder ({f.archived_chat_count})
          </button>
          {showArchived && (
            <div className="mt-3">
              <ChatList
                params={{ folder_id: folderId, archive: 'archived' }}
                empty={<p className="text-muted">No archived chats here.</p>}
              />
            </div>
          )}
        </div>
      )}
    </section>
  )
}
