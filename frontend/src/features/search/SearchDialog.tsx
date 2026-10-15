import { Archive, Search, X } from 'lucide-react'
import { Dialog } from 'radix-ui'
import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { historyItems, useFolders, useHistory } from '../../api/queries'
import { useReturnFocus } from '../../components/focus'

export const SEARCH_DEBOUNCE_MS = 250

export function useDebounced<T>(value: T, ms: number): T {
  const [settled, setSettled] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setSettled(value), ms)
    return () => clearTimeout(t)
  }, [value, ms])
  return settled
}

/** Split plain text around every case-insensitive occurrence of `q` (rendered as text, never HTML). */
export function highlight(text: string, q: string) {
  const parts: { text: string; match: boolean }[] = []
  if (!q) return [{ text, match: false }]
  const lower = text.toLocaleLowerCase()
  const needle = q.toLocaleLowerCase()
  let at = 0
  for (let i = lower.indexOf(needle); i !== -1; i = lower.indexOf(needle, i + needle.length)) {
    if (i > at) parts.push({ text: text.slice(at, i), match: false })
    parts.push({ text: text.slice(i, i + needle.length), match: true })
    at = i + needle.length
  }
  if (at < text.length) parts.push({ text: text.slice(at), match: false })
  return parts
}

function Marked({ text, q }: { text: string; q: string }) {
  return (
    <>
      {highlight(text, q).map((p, i) =>
        p.match ? (
          <mark key={i} className="rounded-sm bg-selection-surface px-0.5 text-text">
            {p.text}
          </mark>
        ) : (
          <span key={i}>{p.text}</span>
        ),
      )}
    </>
  )
}

export function SearchDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const [text, setText] = useState('')
  const [includeArchived, setIncludeArchived] = useState(false)
  const q = useDebounced(text.trim().slice(0, 200), SEARCH_DEBOUNCE_MS)
  // A new key cancels the previous request (TanStack aborts its signal); cursors reset per key.
  const results = useHistory(
    { q, archive: includeArchived ? 'all' : 'active', limit: 20 },
    { enabled: open && q.length > 0 },
  )
  const folders = useFolders()
  const folderName = new Map(folders.data?.map((f) => [f.id, f.name]))
  const items = historyItems(results.data)
  const close = () => onOpenChange(false)
  const returnFocus = useReturnFocus(open)

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50" />
        <Dialog.Content
          onCloseAutoFocus={returnFocus}
          className="fixed top-[10dvh] left-1/2 z-50 flex max-h-[80dvh] w-[min(640px,calc(100vw-24px))] -translate-x-1/2 flex-col rounded-dialog border border-border bg-surface text-text shadow-xl"
        >
          <Dialog.Title className="sr-only">Search chats</Dialog.Title>
          <Dialog.Description className="sr-only">
            Search chat titles and messages. Results open the chat at the matching message.
          </Dialog.Description>
          <div className="flex items-center gap-3 border-b border-border px-4">
            <Search aria-hidden size={18} className="text-muted" />
            <input
              autoFocus
              aria-label="Search chats"
              value={text}
              maxLength={200}
              onChange={(e) => setText(e.target.value)}
              placeholder="Search titles and messages"
              className="min-h-14 flex-1 bg-transparent outline-none placeholder:text-muted"
            />
            {text && (
              <button
                type="button"
                aria-label="Clear search"
                onClick={() => setText('')}
                className="grid size-9 place-items-center rounded-control text-muted hover:text-text"
              >
                <X aria-hidden size={18} />
              </button>
            )}
          </div>
          <div className="flex items-center justify-between px-4 py-2 text-[13px] text-muted">
            <label className="flex min-h-9 cursor-pointer items-center gap-2">
              <input
                type="checkbox"
                checked={includeArchived}
                onChange={(e) => setIncludeArchived(e.target.checked)}
                className="size-4 accent-[var(--accent)]"
              />
              Include archived
            </label>
            <span>Enter a word or phrase; matches are literal.</span>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3" aria-live="polite">
            {!q && <p className="px-3 py-6 text-muted">Type to search your chats.</p>}
            {q && results.isPending && <p className="px-3 py-6 text-muted">Searching…</p>}
            {q && results.isError && (
              <p role="alert" className="px-3 py-6">
                Search failed: {results.error.message}{' '}
                <button type="button" className="underline" onClick={() => void results.refetch()}>
                  Try again
                </button>
              </p>
            )}
            {q && results.isSuccess && items.length === 0 && (
              <div className="px-3 py-6">
                <p>No chats match “{q}”.</p>
                <p className="mt-1 text-[13px] text-muted">
                  {includeArchived
                    ? 'Archived chats were included.'
                    : 'Archived chats are not included; tick Include archived to search them too.'}
                </p>
              </div>
            )}
            <ul className="flex flex-col gap-1">
              {items.map((s) => {
                const m = s.match
                const href =
                  m?.kind === 'message' && m.message_id
                    ? `/rooms/${s.id}?message=${m.message_id}`
                    : `/rooms/${s.id}`
                return (
                  <li key={s.id}>
                    <Link
                      to={href}
                      onClick={close}
                      className="block rounded-control px-3 py-2 hover:bg-surface-subtle"
                    >
                      <span className="flex items-center gap-2 font-medium">
                        <span className="truncate">
                          <Marked text={s.title} q={m?.kind === 'title' ? q : ''} />
                        </span>
                        {s.is_archived && (
                          <span className="inline-flex shrink-0 items-center gap-1 rounded-control border border-border px-1.5 text-[12px] font-normal text-muted">
                            <Archive aria-hidden size={12} /> Archived
                          </span>
                        )}
                      </span>
                      {m?.kind === 'message' && (
                        <span className="mt-0.5 line-clamp-2 block text-[14px] text-muted">
                          <Marked text={m.snippet} q={q} />
                        </span>
                      )}
                      <span className="mt-0.5 block text-[12px] text-muted">
                        {s.folder_id ? (folderName.get(s.folder_id) ?? 'Folder') : 'No folder'}
                        {m?.kind === 'title' ? ' · title match' : ''}
                      </span>
                    </Link>
                  </li>
                )
              })}
            </ul>
            {results.hasNextPage && (
              <button
                type="button"
                onClick={() => void results.fetchNextPage()}
                className="mt-2 ml-3 min-h-9 text-[13px] text-muted underline"
              >
                {results.isFetchingNextPage ? 'Loading…' : 'Load more results'}
              </button>
            )}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
