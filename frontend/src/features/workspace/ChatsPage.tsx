import { Plus } from 'lucide-react'
import { Link, useSearchParams } from 'react-router'
import { ChatList } from './ChatList'

const VIEWS = {
  all: {
    title: 'All chats',
    params: { archive: 'active' as const },
    empty: 'No chats yet. Start one and it will appear here.',
  },
  pinned: {
    title: 'Pinned',
    params: { archive: 'active' as const, pinned: true },
    empty: 'Nothing is pinned. Use a chat’s menu to pin it.',
  },
  archived: {
    title: 'Archived',
    params: { archive: 'archived' as const },
    empty: 'No archived chats. Archiving keeps a chat readable without cluttering history.',
  },
}

export function ChatsPage() {
  const [search] = useSearchParams()
  const filter = (search.get('filter') ?? 'all') as keyof typeof VIEWS
  const view = VIEWS[filter] ?? VIEWS.all
  return (
    <section className="mx-auto max-w-[var(--layout-workspace-max)] px-4 py-8 sm:px-6 lg:px-12">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-[length:var(--text-title)] leading-tight font-semibold">
          {view.title}
        </h1>
        <Link
          to="/"
          className="inline-flex min-h-10 items-center gap-2 rounded-control bg-accent px-4 font-medium text-on-accent hover:bg-accent-hover"
        >
          <Plus aria-hidden size={18} /> New chat
        </Link>
      </div>
      <ChatList
        key={filter}
        params={view.params}
        empty={<p className="text-muted">{view.empty}</p>}
      />
    </section>
  )
}
