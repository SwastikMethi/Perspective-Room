import { ArrowUp, Folder, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router'
import { ApiError, type Schemas } from '../../api/client'
import { useFolders, usePersonas, useSettings } from '../../api/queries'
import { Doodles } from '../../components/Doodles'
import { PersonaRoster } from '../../components/PersonaRoster'
import { StorageNotice } from '../../components/StorageNotice'
import { ROSTER, shortLabel } from '../../lib/personas'
import { newChatKey, useDrafts } from '../../stores/drafts'
import { resolvePending } from './pending'
import { defaultControl, discardPending, PendingConflict, sendNewChat, TurnRejected } from './send'

type Mode = Schemas['Session']['mode']
type PersonaId = Schemas['Session']['selected_persona_ids'][number]

const MODES: { value: Mode; label: string; hint: string }[] = [
  { value: 'jev_guided', label: 'Jev-guided', hint: 'Jev picks who speaks next and checks fit' },
  { value: 'fixed_panel', label: 'Fixed panel', hint: 'perspectives take turns in a fixed order' },
  { value: 'standard', label: 'Standard', hint: 'one assistant answers' },
]

const STARTERS = [
  'A tool-sharing shelf for the people in my building',
  'Making interview practice feel less intimidating for students',
  'Reminder messages that help a small clinic cut missed appointments',
]

export function NewChatPage() {
  const [params, setParams] = useSearchParams()
  const folderId = params.get('folder')
  const ask = params.get('ask')
  const key = newChatKey(folderId)
  const draft = useDrafts((s) => s.drafts[key])
  const setDraft = useDrafts((s) => s.set)
  const personas = usePersonas()
  const folders = useFolders()
  const settings = useSettings()
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<{ text: string; folderGone?: boolean } | null>(null)
  const [mode, setMode] = useState<Mode>('jev_guided')
  const [selected, setSelected] = useState<string[] | null>(null)
  const resumed = useRef(false)
  const box = useRef<HTMLTextAreaElement>(null)

  const defaults = personas.data?.default_selection ?? ['mentor', 'skeptic', 'explorer']
  const target = ask && ROSTER.includes(ask as PersonaId) ? ask : null
  const chosen =
    selected ??
    (target && !defaults.includes(target as PersonaId) ? [...defaults, target] : defaults)
  const folder = folderId ? folders.data?.find((f) => f.id === folderId) : null
  const folderMissing = Boolean(folderId && folders.isSuccess && !folder)
  const notReady = settings.data?.provider_mode === 'live' && !settings.data.openai_configured

  const send = async (idea: string) => {
    if (!idea.trim() || busy || notReady) return
    setBusy(true)
    setError(null)
    try {
      const control = target
        ? {
            ...defaultControl(),
            audience: 'person' as const,
            target_persona_id: target as PersonaId,
          }
        : defaultControl()
      const body: Schemas['SessionCreate'] = {
        idea: idea.trim(),
        mode,
        selected_persona_ids: ROSTER.filter((p) => chosen.includes(p)) as PersonaId[],
        ...(folderId ? { folder_id: folderId } : {}),
      }
      let id: string
      try {
        id = await sendNewChat(key, body, control)
      } catch (e) {
        if (!(e instanceof PendingConflict)) throw e
        const choice = await resolvePending(e)
        if (!choice) return
        const earlier = useDrafts.getState().get(key)?.pending?.createBody
        if (choice === 'discard' || !earlier) discardPending(key)
        id = await sendNewChat(key, choice === 'resend' && earlier ? earlier : body, control)
      }
      navigate(`/rooms/${id}`)
    } catch (e) {
      if (e instanceof TurnRejected) {
        // The chat was created; keep the text as that room's draft instead of retrying forever.
        useDrafts.getState().clear(key)
        useDrafts.getState().set(e.sessionId, { text: idea.trim() })
        navigate(`/rooms/${e.sessionId}`)
        return
      }
      setError(
        e instanceof ApiError && e.code === 'folder_missing'
          ? { text: 'That folder no longer exists, so the chat was not created.', folderGone: true }
          : {
              text: e instanceof ApiError ? e.error.message : 'Sending failed. Your text is kept.',
            },
      )
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

  const moveToNoFolder = () => {
    const text = draft?.text ?? ''
    const existing = useDrafts.getState().get(newChatKey(null))?.text.trim()
    useDrafts.getState().clear(key)
    // Never overwrite another unsent draft: keep both texts (M4).
    useDrafts.getState().set(newChatKey(null), {
      text: existing && existing !== text.trim() ? `${existing}\n\n${text}` : text,
      pending: undefined,
    })
    params.delete('folder')
    setParams(params)
    setError(null)
  }

  return (
    <section className="relative mx-auto max-w-[var(--layout-workspace-max)] px-4 py-8 sm:px-6 lg:px-12">
      <Doodles className="absolute top-4 right-6 w-56 lg:right-12" />
      <h1 className="max-w-[24ch] text-[length:var(--text-title)] leading-tight font-semibold sm:text-[40px]">
        What would you like to think through?
      </h1>
      {folderId && (
        <p className="mt-3 inline-flex items-center gap-2 rounded-control border border-border bg-surface py-1 pr-1 pl-3 text-[14px]">
          <Folder aria-hidden size={15} />
          {folderMissing ? 'Folder no longer exists' : `In ${folder?.name ?? 'folder'}`}
          <button
            type="button"
            aria-label="Start without a folder"
            onClick={moveToNoFolder}
            className="grid size-7 place-items-center rounded-control hover:bg-surface-subtle"
          >
            <X aria-hidden size={14} />
          </button>
        </p>
      )}
      <form
        className="mt-6"
        onSubmit={(e) => {
          e.preventDefault()
          void send(draft?.text ?? '')
        }}
      >
        <div className="flex items-end gap-2 rounded-card border border-border bg-surface p-2 focus-within:border-selection-border">
          <label htmlFor="new-idea" className="sr-only">
            Your idea
          </label>
          <textarea
            id="new-idea"
            ref={box}
            rows={3}
            maxLength={16000}
            value={draft?.text ?? ''}
            onChange={(e) => setDraft(key, { text: e.target.value })}
            onKeyDown={(e) => {
              if (e.nativeEvent.isComposing || e.keyCode === 229) return
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                void send(draft?.text ?? '')
              }
            }}
            placeholder="Describe an idea, a decision or a project…"
            className="field-sizing-content max-h-72 min-h-24 flex-1 resize-none bg-transparent p-2 text-[17px] text-text outline-none placeholder:text-muted"
          />
          <button
            type="submit"
            disabled={busy || notReady || !(draft?.text ?? '').trim() || folderMissing}
            className="inline-flex min-h-11 shrink-0 items-center gap-2 rounded-control bg-accent px-4 font-medium text-on-accent hover:bg-accent-hover disabled:opacity-60"
          >
            <ArrowUp aria-hidden size={18} strokeWidth={2.5} />
            {busy ? 'Starting…' : 'Send'}
          </button>
        </div>
        <div className="mt-1 flex flex-wrap justify-between gap-2 px-1 text-[13px] text-muted">
          <StorageNotice />
          <span className="ml-auto max-sm:hidden">Enter to send · Shift+Enter for a new line</span>
        </div>
        {notReady && (
          <p role="alert" className="mt-2 text-[14px]">
            Live replies need <code>OPENAI_API_KEY</code> in <code>.env</code>. Add it and restart,
            or run with <code>APP_PROVIDER_MODE=demo</code> for a labeled offline demo.
          </p>
        )}
        {target && (
          <p className="mt-2 text-[14px] text-muted">
            The first question goes to {shortLabel(target)}.{' '}
            <button type="button" className="underline" onClick={() => setParams({})}>
              Ask everyone instead
            </button>
          </p>
        )}
        {error && (
          <p role="alert" className="mt-2 text-[14px] text-danger">
            {error.text}{' '}
            {error.folderGone && (
              <button type="button" className="underline" onClick={moveToNoFolder}>
                Start it without a folder
              </button>
            )}
          </p>
        )}
      </form>
      {!(draft?.text ?? '').trim() && (
        <div className="mt-4 flex flex-wrap gap-2" aria-label="Starters">
          {STARTERS.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => {
                setDraft(key, { text: s })
                box.current?.focus()
              }}
              className="min-h-10 rounded-control border border-border px-3 text-left text-[14px] text-muted hover:border-selection-border hover:text-text"
            >
              {s}
            </button>
          ))}
        </div>
      )}
      <fieldset className="mt-8">
        <legend className="text-[18px] font-semibold">How the room answers</legend>
        <div className="mt-2 flex flex-wrap gap-2">
          {MODES.map((m) => (
            <label
              key={m.value}
              className={
                'flex min-h-11 cursor-pointer items-center gap-2 rounded-control border px-3 text-[14px] ' +
                (mode === m.value
                  ? 'border-selection-border bg-selection-surface'
                  : 'border-border')
              }
            >
              <input
                type="radio"
                name="mode"
                value={m.value}
                checked={mode === m.value}
                onChange={() => setMode(m.value)}
                className="size-4 accent-[var(--accent)]"
              />
              <span className="font-medium">{m.label}</span>
              <span className="text-muted">— {m.hint}</span>
            </label>
          ))}
        </div>
      </fieldset>
      {personas.data && (
        <PersonaRoster
          selected={chosen}
          personas={personas.data.items}
          defaultSelection={defaults}
          onChange={setSelected}
          standard={mode === 'standard'}
        />
      )}
    </section>
  )
}
