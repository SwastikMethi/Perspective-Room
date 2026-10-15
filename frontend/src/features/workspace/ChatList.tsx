import { Loader2, Pin } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router'
import type { Schemas } from '../../api/client'
import { type HistoryParams, historyItems, useFolders, useHistory } from '../../api/queries'
import { ChatMenu } from './ChatRow'

const when = (iso: string) =>
  new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })

function ChatListItem({ chat, folder }: { chat: Schemas['SessionSummary']; folder?: string }) {
  return (
    <li className="group flex items-center gap-2 rounded-card border border-border bg-surface pr-2 hover:border-selection-border">
      <Link to={`/rooms/${chat.id}`} className="min-w-0 flex-1 px-4 py-3">
        <span className="flex items-center gap-2">
          <span className="truncate font-medium" title={chat.title}>
            {chat.title}
          </span>
          {chat.is_pinned && <Pin aria-label="Pinned" size={14} className="shrink-0 text-muted" />}
          {chat.active_run_id && (
            <span className="inline-flex shrink-0 items-center gap-1 text-[13px] text-muted">
              <Loader2 aria-hidden size={14} className="animate-spin motion-reduce:animate-none" />
              Working
            </span>
          )}
        </span>
        <span className="mt-0.5 block text-[13px] text-muted">
          {folder ?? 'No folder'} · last active {when(chat.last_activity_at)}
          {chat.is_archived ? ' · archived' : ''}
        </span>
      </Link>
      <ChatMenu chat={chat} />
    </li>
  )
}

/** A paginated chat list with distinct loading, error and empty states. */
export function ChatList({ params, empty }: { params: HistoryParams; empty: ReactNode }) {
  const q = useHistory(params)
  const folders = useFolders()
  const names = new Map(folders.data?.map((f) => [f.id, f.name]))
  const chats = historyItems(q.data)
  if (q.isPending) return <p className="text-muted">Loading chats…</p>
  if (q.isError)
    return (
      <p role="alert">
        Chats could not load: {q.error.message}{' '}
        <button type="button" className="underline" onClick={() => void q.refetch()}>
          Try again
        </button>
      </p>
    )
  if (chats.length === 0) return <>{empty}</>
  return (
    <>
      <ul className="flex flex-col gap-2">
        {chats.map((c) => (
          <ChatListItem
            key={c.id}
            chat={c}
            folder={c.folder_id ? names.get(c.folder_id) : undefined}
          />
        ))}
      </ul>
      {q.hasNextPage && (
        <button
          type="button"
          onClick={() => void q.fetchNextPage()}
          disabled={q.isFetchingNextPage}
          className="mt-4 min-h-10 rounded-control border border-border px-4 hover:bg-surface-subtle"
        >
          {q.isFetchingNextPage ? 'Loading…' : 'Load more'}
        </button>
      )}
    </>
  )
}
