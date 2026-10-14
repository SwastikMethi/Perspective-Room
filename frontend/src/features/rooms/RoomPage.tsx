import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useParams } from 'react-router'
import { ApiError, api, type Schemas, unwrap } from '../../api/client'
import { keys, useMessages, usePersonas, useRun, useSession } from '../../api/queries'
import { useRunEvents } from '../../api/sse'
import { useDrafts } from '../../stores/drafts'
import { defaultControl, sendTurn } from './send'

const ACTIVE = ['queued', 'running', 'cancelling']

function Contribution({ message, name }: { message: Schemas['Message']; name: string }) {
  const c = message.contribution
  return (
    <article
      data-testid="contribution"
      data-persona={message.persona_id ?? 'assistant'}
      className="rounded-card border border-border bg-surface p-4"
    >
      <p className="text-[13px] tracking-[0.12em] text-muted uppercase">{name}</p>
      {c && (
        <>
          <h3 className="mt-1 text-lg font-semibold">{c.headline}</h3>
          {c.blocks.map((b, i) => (
            <p key={i} className="mt-2 text-muted">
              {b.text}
            </p>
          ))}
        </>
      )}
      {!c && message.text && <p className="mt-2">{message.text}</p>}
    </article>
  )
}

export function RoomPage() {
  const { id = '' } = useParams()
  const qc = useQueryClient()
  const session = useSession(id)
  const messages = useMessages(id)
  const personas = usePersonas()
  const activeRunId = session.data?.active_run_id ?? null
  const run = useRun(activeRunId)
  useRunEvents(id, activeRunId)
  const draft = useDrafts((s) => s.drafts[id])
  const setDraft = useDrafts((s) => s.set)
  const [error, setError] = useState<string | null>(null)
  const names = new Map(personas.data?.items.map((p) => [p.id, p.display_name]))
  const running = Boolean(activeRunId) && ACTIVE.includes(run.data?.status ?? 'queued')

  const send = async () => {
    const text = (draft?.text ?? '').trim()
    if (!text || running || !session.data) return
    setError(null)
    try {
      const r = await sendTurn(id, {
        expected_version: session.data.version,
        message: text,
        control: defaultControl(),
      })
      qc.setQueryData(keys.run(r.id), r)
      await qc.invalidateQueries({ queryKey: keys.session(id) })
      await qc.invalidateQueries({ queryKey: keys.messages(id) })
    } catch (e) {
      setError(e instanceof ApiError ? e.error.message : 'Sending failed.')
    }
  }

  const stop = async () => {
    if (!activeRunId) return
    const r = await unwrap(
      api.POST('/api/v1/runs/{run_id}/cancel', { params: { path: { run_id: activeRunId } } }),
    )
    qc.setQueryData(keys.run(r.id), r)
  }

  if (session.isError) return <p className="p-8">This chat could not be loaded.</p>
  return (
    <section className="mx-auto flex max-w-[var(--layout-workspace-max)] flex-col gap-4 px-4 py-6 sm:px-6 lg:px-12">
      <h1 className="text-[length:var(--text-title)] leading-tight font-semibold">
        {session.data?.title ?? ' '}
      </h1>
      <ol className="flex flex-col gap-3" aria-label="Conversation">
        {messages.data?.items.map((m) => (
          <li key={m.id}>
            {m.role === 'user' ? (
              <p data-testid="user-message" className="rounded-card bg-surface-subtle p-4">
                {m.text}
              </p>
            ) : (
              <Contribution
                message={m}
                name={m.persona_id ? (names.get(m.persona_id) ?? m.persona_id) : 'Moderator'}
              />
            )}
          </li>
        ))}
      </ol>
      {running && (
        <p role="status" data-testid="run-status" className="text-sm text-muted">
          {run.data?.status === 'cancelling'
            ? 'Stopping…'
            : `Working: ${run.data?.stage ?? 'queued'}`}
        </p>
      )}
      <form
        onSubmit={(e) => {
          e.preventDefault()
          void send()
        }}
        className="flex gap-2"
      >
        <label htmlFor="composer" className="sr-only">
          Message
        </label>
        <textarea
          id="composer"
          rows={2}
          value={draft?.text ?? ''}
          onChange={(e) => setDraft(id, { text: e.target.value })}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault()
              void send()
            }
          }}
          placeholder="Bring another thought to the room…"
          className="flex-1 rounded-card border border-border bg-surface p-3"
        />
        {running ? (
          <button
            type="button"
            onClick={() => void stop()}
            className="min-h-11 rounded-control border border-border px-4"
          >
            Stop
          </button>
        ) : (
          <button type="submit" className="min-h-11 rounded-control bg-accent px-4 text-on-accent">
            Send
          </button>
        )}
      </form>
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
    </section>
  )
}
