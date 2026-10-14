// Query keys and fetchers shared across features.
import { useQuery } from '@tanstack/react-query'
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
