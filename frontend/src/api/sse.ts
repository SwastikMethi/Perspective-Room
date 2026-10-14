// Reconnectable, read-only subscription to a run's persisted events. Reconnecting never resubmits
// work: the server only replays what is stored. Events are deduplicated by their server ID.
import { useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { api, unwrap } from './client'
import { EVENT_TYPES, isTerminal, type RunEventEnvelope } from './events'
import { keys, upsertMessages } from './queries'

interface SubscribeOptions {
  runId: string
  after: string | null
  onEvent: (e: RunEventEnvelope) => void
  onTerminal: (e: RunEventEnvelope) => void
  /** The stream ended without a terminal event (server error, 409 cursor, network). */
  onLost: (lastEventId: string | null) => void
  EventSourceImpl?: typeof EventSource
}

export function subscribeRunEvents(opts: SubscribeOptions) {
  const Impl = opts.EventSourceImpl ?? EventSource
  let last = opts.after
  const seen = new Set<string>()
  const url = `/api/v1/runs/${opts.runId}/events${last ? `?after=${encodeURIComponent(last)}` : ''}`
  const es = new Impl(url)
  let done = false

  const handle = (raw: MessageEvent) => {
    const event = JSON.parse(raw.data) as RunEventEnvelope
    if (seen.has(event.id)) return
    seen.add(event.id)
    last = event.id
    opts.onEvent(event)
    if (isTerminal(event.type)) {
      done = true
      es.close()
      opts.onTerminal(event)
    }
  }
  for (const type of EVENT_TYPES) es.addEventListener(type, handle as EventListener)
  es.onerror = () => {
    // CONNECTING means the browser is already retrying with Last-Event-ID; CLOSED is final.
    if (!done && es.readyState === Impl.CLOSED) opts.onLost(last)
  }
  return {
    close: () => {
      done = true
      es.close()
    },
    lastEventId: () => last,
  }
}

// Last delivered event per run, so returning to a chat resumes instead of replaying everything.
const cursors = new Map<string, string>()

/** Attach the current room to its active run. Leaving the room closes the view, not the run. */
export function useRunEvents(sessionId: string, runId: string | null | undefined) {
  const qc = useQueryClient()
  useEffect(() => {
    if (!runId) return
    let sub: ReturnType<typeof subscribeRunEvents> | null = null
    let retry: ReturnType<typeof setTimeout> | undefined
    let stopped = false

    const refreshSnapshot = async () => {
      const run = await unwrap(
        api.GET('/api/v1/runs/{run_id}', { params: { path: { run_id: runId } } }),
      )
      qc.setQueryData(keys.run(runId), run)
      await qc.invalidateQueries({ queryKey: keys.messages(sessionId) })
      return run
    }

    const connect = (after: string | null) => {
      sub = subscribeRunEvents({
        runId,
        after,
        onEvent: (e) => {
          cursors.set(runId, e.id)
          if (e.type === 'message.completed') {
            // An in-flight refetch must not overwrite the card that just arrived.
            void qc.cancelQueries({ queryKey: keys.messages(sessionId) })
            qc.setQueryData(keys.messages(sessionId), (old) =>
              upsertMessages(old as never, [e.data.message]),
            )
          }
          if (e.type === 'research.completed')
            void qc.invalidateQueries({ queryKey: keys.sources(sessionId) })
          qc.setQueryData(keys.runEvents(runId), (old: RunEventEnvelope[] | undefined) => [
            ...(old ?? []).filter((x) => x.id !== e.id),
            e,
          ])
        },
        onTerminal: (e) => {
          if ('run' in e.data) qc.setQueryData(keys.run(runId), e.data.run)
          void qc.invalidateQueries({ queryKey: keys.session(sessionId) })
          void qc.invalidateQueries({ queryKey: keys.messages(sessionId) })
          void qc.invalidateQueries({ queryKey: ['history'] })
          void qc.invalidateQueries({ queryKey: keys.ideas(sessionId) })
        },
        onLost: () => {
          if (stopped) return
          // The cursor may be the reason (409): replay from the start; IDs dedupe the cards.
          cursors.delete(runId)
          void refreshSnapshot()
            .then((run) => {
              if (!stopped && ['queued', 'running', 'cancelling'].includes(run.status))
                retry = setTimeout(() => connect(null), 1000)
            })
            .catch(() => {
              if (!stopped) retry = setTimeout(() => connect(null), 3000)
            })
        },
      })
    }
    connect(cursors.get(runId) ?? null)
    return () => {
      stopped = true
      clearTimeout(retry)
      sub?.close()
    }
  }, [qc, sessionId, runId])
}
