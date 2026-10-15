// Query keys and fetchers shared across features.
import { useInfiniteQuery, useQuery } from '@tanstack/react-query'
import { api, type Schemas, unwrap } from './client'

export const keys = {
  settings: ['settings'] as const,
  personas: ['personas'] as const,
  session: (id: string) => ['session', id] as const,
  messages: (id: string) => ['messages', id] as const,
  run: (id: string) => ['run', id] as const,
  runEvents: (id: string) => ['run-events', id] as const,
  sources: (id: string) => ['sources', id] as const,
  ideas: (id: string) => ['ideas', id] as const,
  history: (params: HistoryParams) => ['history', params] as const,
  folders: ['folders'] as const,
  folder: (id: string) => ['folders', id] as const,
}

export interface HistoryParams {
  q?: string
  folder_id?: string
  unfiled?: boolean
  pinned?: boolean
  archive?: 'active' | 'archived' | 'all'
  limit?: number
}

export type MessageList = Schemas['MessageList']

/** Merge messages by id, ordered by sequence: SSE replays and refetches never duplicate a card. */
export function upsertMessages(
  list: MessageList | undefined,
  incoming: Schemas['Message'][],
): MessageList {
  const byId = new Map((list?.items ?? []).map((m) => [m.id, m]))
  for (const m of incoming) byId.set(m.id, m)
  return {
    items: [...byId.values()].sort((a, b) => a.sequence - b.sequence),
    next_cursor: list?.next_cursor ?? null,
    previous_cursor: list?.previous_cursor ?? null,
  }
}

export function useSettings() {
  return useQuery({
    queryKey: keys.settings,
    queryFn: () => unwrap(api.GET('/api/v1/settings')),
    staleTime: 60_000,
  })
}

export function usePersonas() {
  return useQuery({
    queryKey: keys.personas,
    queryFn: () => unwrap(api.GET('/api/v1/personas')),
    staleTime: Infinity,
  })
}

export function useSession(id: string) {
  return useQuery({
    queryKey: keys.session(id),
    queryFn: () =>
      unwrap(api.GET('/api/v1/sessions/{session_id}', { params: { path: { session_id: id } } })),
  })
}

export function useMessages(id: string) {
  return useQuery({
    queryKey: keys.messages(id),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/sessions/{session_id}/messages', {
          params: { path: { session_id: id }, query: { limit: 50 } },
        }),
      ),
  })
}

export function useRun(id: string | null | undefined) {
  return useQuery({
    queryKey: keys.run(id ?? 'none'),
    enabled: Boolean(id),
    queryFn: () => unwrap(api.GET('/api/v1/runs/{run_id}', { params: { path: { run_id: id! } } })),
  })
}

/** Paginated, lightweight chat lists (never transcripts). Pages dedupe by session ID. */
export function useHistory(params: HistoryParams, opts: { enabled?: boolean } = {}) {
  return useInfiniteQuery({
    queryKey: keys.history(params),
    enabled: opts.enabled ?? true,
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) =>
      unwrap(
        api.GET('/api/v1/sessions', {
          params: { query: { limit: 30, ...params, ...(pageParam ? { cursor: pageParam } : {}) } },
          signal,
        }),
      ),
    getNextPageParam: (last) => last.next_cursor,
    // doc 14: poll lightweight history only while a listed chat is working; refetch on focus.
    refetchInterval: (query) =>
      query.state.data?.pages.some((p) => p.items.some((s) => s.active_run_id)) ? 5000 : false,
    refetchOnWindowFocus: true,
  })
}

export function historyItems(data: { pages: Schemas['SessionList'][] } | undefined) {
  const seen = new Set<string>()
  return (data?.pages ?? [])
    .flatMap((p) => p.items)
    .filter((s) => !seen.has(s.id) && Boolean(seen.add(s.id)))
}

export function useFolders() {
  return useQuery({
    queryKey: keys.folders,
    queryFn: async () => {
      const items: Schemas['Folder'][] = []
      let cursor: string | null = null
      do {
        const page: Schemas['FolderList'] = await unwrap(
          api.GET('/api/v1/folders', {
            params: { query: { limit: 100, ...(cursor ? { cursor } : {}) } },
          }),
        )
        items.push(...page.items)
        cursor = page.next_cursor
      } while (cursor)
      return items
    },
  })
}

export function useIdeas(sessionId: string) {
  return useQuery({
    queryKey: keys.ideas(sessionId),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/sessions/{session_id}/idea-cards', {
          params: { path: { session_id: sessionId } },
        }),
      ),
  })
}

export function useSources(sessionId: string) {
  return useQuery({
    queryKey: keys.sources(sessionId),
    queryFn: async () => {
      const items: Schemas['Source'][] = []
      let cursor: string | null = null
      do {
        const page: Schemas['SourceList'] = await unwrap(
          api.GET('/api/v1/sessions/{session_id}/sources', {
            params: {
              path: { session_id: sessionId },
              query: { limit: 100, ...(cursor ? { cursor } : {}) },
            },
          }),
        )
        items.push(...page.items)
        cursor = page.next_cursor
      } while (cursor)
      return items
    },
  })
}
