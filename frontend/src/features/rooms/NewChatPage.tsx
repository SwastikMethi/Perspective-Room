import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router'
import { ApiError } from '../../api/client'
import { useDrafts, newChatKey } from '../../stores/drafts'
import { sendNewChat, TurnRejected } from './send'

export function NewChatPage() {
  const key = newChatKey()
  const draft = useDrafts((s) => s.drafts[key])
  const setDraft = useDrafts((s) => s.set)
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const resumed = useRef(false)

  const send = async (idea: string) => {
    if (!idea.trim() || busy) return
    setBusy(true)
    setError(null)
    try {
      const id = await sendNewChat(key, { idea: idea.trim() })
      navigate(`/rooms/${id}`)
    } catch (e) {
      if (e instanceof TurnRejected) {
        // The chat was created; keep the text as that room's draft instead of retrying forever.
        useDrafts.getState().clear(key)
        useDrafts.getState().set(e.sessionId, { text: idea.trim() })
        navigate(`/rooms/${e.sessionId}`)
        return
      }
      setError(e instanceof ApiError ? e.error.message : 'Sending failed.')
    } finally {
      setBusy(false)
    }
  }

  // A refresh during the first Send resumes it with the same keys and bodies.
  useEffect(() => {
    if (!resumed.current && draft?.pending?.createBody) {
      resumed.current = true
      void send(draft.pending.createBody.idea)
    }
  })

  return (
    <section className="mx-auto max-w-[var(--layout-workspace-max)] px-4 py-8 sm:px-6 lg:px-12">
      <h1 className="text-[length:var(--text-title)] leading-tight font-semibold">
        What would you like to think through?
      </h1>
      <form
        className="mt-6"
        onSubmit={(e) => {
          e.preventDefault()
          void send(draft?.text ?? '')
        }}
      >
        <label htmlFor="new-idea" className="sr-only">
          Your idea
        </label>
        <textarea
          id="new-idea"
          rows={3}
          value={draft?.text ?? ''}
          onChange={(e) => setDraft(key, { text: e.target.value })}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault()
              void send(draft?.text ?? '')
            }
          }}
          placeholder="Describe an idea, a decision or a project…"
          className="w-full rounded-card border border-border bg-surface p-4 text-text"
        />
        {error && (
          <p role="alert" className="mt-2 text-sm text-danger">
            {error}
          </p>
        )}
        <button
          type="submit"
          disabled={busy || !(draft?.text ?? '').trim()}
          className="mt-3 min-h-11 rounded-control bg-accent px-5 font-medium text-on-accent disabled:opacity-60"
        >
          {busy ? 'Starting…' : 'Send'}
        </button>
      </form>
    </section>
  )
}
