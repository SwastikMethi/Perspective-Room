import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowDown, Bookmark, MoreHorizontal, RotateCcw, SlidersHorizontal } from 'lucide-react'
import { DropdownMenu, Popover } from 'radix-ui'
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'
import { ApiError, api, newIdempotencyKey, type Schemas, unwrap } from '../../api/client'
import type { RunEventEnvelope } from '../../api/events'
import {
  keys,
  type MessageList,
  upsertMessages,
  useFolders,
  useIdeas,
  useMessages,
  usePersonas,
  useRun,
  useSession,
  useSources,
} from '../../api/queries'
import { useRunEvents } from '../../api/sse'
import { dialogs, notify } from '../../components/Dialogs'
import { Doodles } from '../../components/Doodles'
import { HeaderActions } from '../../components/HeaderActions'
import { PersonaRoster } from '../../components/PersonaRoster'
import { shortLabel } from '../../lib/personas'
import { useDrafts } from '../../stores/drafts'
import { exportChat, organize } from '../workspace/actions'
import { ChatMenuItems, MenuItem, menuContent } from '../workspace/ChatRow'
import { Composer } from './Composer'
import { warningText } from './copy'
import { DetailsDrawer, patchBrief } from './DetailsDrawer'
import { groupTurns } from './grouping'
import { useRoomActions } from './roomActions'
import { STAGE_TEXT, useRoomUi } from './roomUi'
import { resolvePending } from './pending'
import { discardPending, PendingConflict, sendTurn } from './send'
import { RoomContext, TurnGroup } from './TurnGroup'

const ACTIVE = ['queued', 'running', 'cancelling']
const RETRYABLE = ['partial', 'failed', 'interrupted', 'cancelled']
const MODE_LABEL = { jev_guided: 'Jev-guided', fixed_panel: 'Fixed panel', standard: 'Standard' }

function mergePage(
  old: MessageList | undefined,
  page: MessageList,
  dir: 'older' | 'newer',
): MessageList {
  const merged = upsertMessages(old, page.items)
  return {
    ...merged,
    previous_cursor: dir === 'older' ? page.previous_cursor : (old?.previous_cursor ?? null),
    next_cursor: dir === 'newer' ? page.next_cursor : (old?.next_cursor ?? null),
  }
}

/** Queued / drafting / done / missing per requested slot, from the run's own events. */
function RunSlots({ run, events }: { run: Schemas['Run']; events: RunEventEnvelope[] }) {
  const queued = events.find((e) => e.type === 'run.queued' || e.type === 'run.started')
  const slots = queued && 'slots' in queued.data ? queued.data.slots : []
  const done = new Set(
    events.flatMap((e) =>
      e.type === 'message.completed'
        ? [e.data.message.persona_id ?? (e.data.message.summary ? 'summary' : 'assistant')]
        : [],
    ),
  )
  const stage = [...events].reverse().find((e) => e.type === 'run.stage')
  const drafting = stage?.type === 'run.stage' ? stage.data.persona_id : null
  const terminal = events.find((e) => e.type.startsWith('run.') && 'missing_persona_ids' in e.data)
  const missing = new Set(
    terminal && 'missing_persona_ids' in terminal.data ? terminal.data.missing_persona_ids : [],
  )
  const active = ACTIVE.includes(run.status)
  const label = (s: string) =>
    s === 'assistant' ? 'Assistant' : s === 'summary' ? 'Summary' : shortLabel(s)
  const state = (s: string) =>
    done.has(s)
      ? 'done'
      : missing.has(s)
        ? 'not produced'
        : s === drafting && active
          ? 'drafting'
          : active
            ? 'waiting'
            : 'not produced'
  return (
    <div className="flex flex-wrap items-center gap-2 text-[14px]" data-testid="run-slots">
      <p role="status" className="text-muted" data-testid="run-status">
        {run.status === 'cancelling'
          ? 'Stopping…'
          : active
            ? `${STAGE_TEXT[run.stage] ?? run.stage}${drafting ? ` — ${shortLabel(drafting)}` : ''}…`
            : null}
      </p>
      {slots.length > 0
        ? slots.map((s) => (
            <span key={s} className="rounded-control border border-border px-2 py-0.5">
              {label(s)}: {state(s)}
            </span>
          ))
        : active && (
            <span className="rounded-control border border-border px-2 py-0.5">
              {run.published_count} of up to {run.requested_count} replies
            </span>
          )}
    </div>
  )
}

function RoomSettings({
  session,
  disabled,
}: {
  session: Schemas['Session']
  disabled: string | null
}) {
  const qc = useQueryClient()
  const save = async (settings: Schemas['SessionSettings']) => {
    try {
      const next = await unwrap(
        api.PATCH('/api/v1/sessions/{session_id}', {
          params: { path: { session_id: session.id } },
          body: { expected_version: session.version, settings },
        }),
      )
      qc.setQueryData(keys.session(session.id), next)
    } catch (e) {
      notify(e instanceof ApiError ? e.error.message : 'Settings were not saved.', 'error')
    }
  }
  return (
    <Popover.Root>
      <Popover.Trigger
        aria-label="Room settings"
        className="grid size-10 place-items-center rounded-control border border-border text-muted hover:text-text"
      >
        <SlidersHorizontal aria-hidden size={18} />
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          align="end"
          sideOffset={6}
          className="z-50 w-72 rounded-card border border-border bg-surface p-4 text-text shadow-xl"
        >
          <p className="font-semibold">Room settings</p>
          {disabled && <p className="mt-1 text-[13px] text-muted">{disabled}</p>}
          <label className="mt-3 block text-[14px]" htmlFor="rs-research">
            Research for this chat
          </label>
          <select
            id="rs-research"
            disabled={Boolean(disabled)}
            value={session.settings.research_policy}
            onChange={(e) =>
              void save({ ...session.settings, research_policy: e.target.value as 'auto' | 'off' })
            }
            className="mt-1 min-h-10 w-full rounded-control border border-border bg-surface px-2"
          >
            <option value="auto">Auto — search when current facts matter</option>
            <option value="off">Off — never search</option>
          </select>
          <label className="mt-3 block text-[14px]" htmlFor="rs-auto">
            Replies per automatic turn
          </label>
          <select
            id="rs-auto"
            disabled={Boolean(disabled)}
            value={session.settings.auto_contributions}
            onChange={(e) =>
              void save({ ...session.settings, auto_contributions: Number(e.target.value) })
            }
            className="mt-1 min-h-10 w-full rounded-control border border-border bg-surface px-2"
          >
            {[1, 2, 3].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
}

export function RoomPage() {
  const { id = '' } = useParams()
  const [search, setSearch] = useSearchParams()
  const anchor = search.get('message')
  const qc = useQueryClient()
  const session = useSession(id)
  const messages = useMessages(id)
  const personas = usePersonas()
  const ideas = useIdeas(id)
  const sources = useSources(id)
  const folders = useFolders()
  const s = session.data
  const activeRunId = s?.active_run_id ?? null
  const activeRun = useRun(activeRunId)
  useRunEvents(id, activeRunId)
  const items = useMemo(() => messages.data?.items ?? [], [messages.data])
  const groups = useMemo(() => groupTurns(items), [items])
  const lastUser = [...items].reverse().find((m) => m.role === 'user')
  const latestRunId = activeRunId ?? lastUser?.run_id ?? null
  const latestRun = useRun(latestRunId)
  const shownRunId = activeRunId ?? lastUser?.run_id ?? null
  const events = useQuery<RunEventEnvelope[]>({
    queryKey: keys.runEvents(shownRunId ?? 'none'),
    queryFn: () => [],
    enabled: false,
    initialData: [],
  }).data
  const running = Boolean(activeRunId) && ACTIVE.includes(activeRun.data?.status ?? 'queued')
  const names = useMemo(
    () => new Map(personas.data?.items.map((p) => [p.id, p.display_name])),
    [personas.data],
  )
  const sourceMap = useMemo(
    () => new Map((sources.data ?? []).map((x) => [x.id, x])),
    [sources.data],
  )
  const saved = useMemo(
    () => new Map((ideas.data?.items ?? []).map((c) => [c.message_id, c])),
    [ideas.data],
  )
  const actions = useRoomActions(s)
  const reset = useRoomUi((st) => st.reset)
  const [error, setError] = useState<string | null>(null)
  const [stale, setStale] = useState(false)
  const [atBottom, setAtBottom] = useState(true)
  const [unseen, setUnseen] = useState(false)
  const endRef = useRef<HTMLDivElement>(null)
  const count = useRef(0)
  const pendingScroll = useRef<string | null>(null)

  // Scroll to a deep-linked message once it is actually rendered.
  useEffect(() => {
    const target = pendingScroll.current
    const el = target ? document.getElementById(`m-${target}`) : null
    if (el) {
      el.scrollIntoView({ block: 'center' })
      pendingScroll.current = null
    }
  })

  useEffect(() => reset(), [id, reset])

  // Deep link (?message=): load a window around it, scroll and highlight; nothing reruns.
  useEffect(() => {
    if (!anchor) return
    let cancelled = false
    void unwrap(
      api.GET('/api/v1/sessions/{session_id}/messages', {
        params: { path: { session_id: id }, query: { around_message_id: anchor, limit: 30 } },
      }),
    )
      .then(async (page) => {
        if (cancelled) return
        await qc.cancelQueries({ queryKey: keys.messages(id) }) // the latest page must not win
        qc.setQueryData(keys.messages(id), page)
        pendingScroll.current = anchor
        useRoomUi.setState({ highlight: anchor })
      })
      .catch(
        () =>
          !cancelled &&
          setError('That message is no longer in this chat. It may have been deleted.'),
      )
    return () => {
      cancelled = true
    }
  }, [anchor, id, qc])

  // Track whether the reader is at the end; never force-scroll someone reading earlier turns.
  useEffect(() => {
    const main = document.getElementById('main')
    if (!main) return
    const onScroll = () => {
      const near = main.scrollHeight - main.scrollTop - main.clientHeight < 160
      setAtBottom(near)
      if (near) setUnseen(false)
    }
    main.addEventListener('scroll', onScroll, { passive: true })
    return () => main.removeEventListener('scroll', onScroll)
  }, [])
  useLayoutEffect(() => {
    const grew = items.length > count.current
    const first = count.current === 0
    count.current = items.length
    if (!grew || anchor) return
    if (first) {
      // Opening a chat lands on its latest turn; a one-turn chat stays at the top.
      if (groups.length > 1) endRef.current?.scrollIntoView({ block: 'end' })
    } else if (atBottom) endRef.current?.scrollIntoView({ block: 'end' })
    else setUnseen(true)
  }, [items.length, atBottom, anchor, groups.length])

  const registerFocus = useCallback((f: () => void) => useRoomUi.setState({ focusComposer: f }), [])

  const loadPage = async (dir: 'older' | 'newer') => {
    const cursor = dir === 'older' ? messages.data?.previous_cursor : messages.data?.next_cursor
    if (!cursor) return
    const main = document.getElementById('main')
    const before = main ? main.scrollHeight - main.scrollTop : 0
    const page = await unwrap(
      api.GET('/api/v1/sessions/{session_id}/messages', {
        params: { path: { session_id: id }, query: { cursor, limit: 50 } },
      }),
    )
    qc.setQueryData(keys.messages(id), (old: MessageList | undefined) => mergePage(old, page, dir))
    if (dir === 'older' && main)
      requestAnimationFrame(() => (main.scrollTop = main.scrollHeight - before))
  }

  const send = async (
    text: string,
    control: Schemas['TurnControl'],
    draftKey: string = id, // a summary uses its own key so it never replays a pending message
  ) => {
    if (!s) return
    setError(null)
    setStale(false)
    try {
      const body = { expected_version: s.version, message: text.trim(), control }
      let r: Schemas['Run']
      try {
        r = await sendTurn(id, body, draftKey)
      } catch (e) {
        if (!(e instanceof PendingConflict)) throw e
        const choice = await resolvePending(e)
        if (!choice) return
        const earlier = useDrafts.getState().get(draftKey)?.pending?.turnBody
        if (choice === 'discard' || !earlier) discardPending(draftKey)
        r = await sendTurn(id, choice === 'resend' && earlier ? earlier : body, draftKey)
      }
      qc.setQueryData(keys.run(r.id), r)
      if (anchor) setSearch({}, { replace: true })
      await qc.invalidateQueries({ queryKey: keys.session(id) })
      await qc.invalidateQueries({ queryKey: ['history'] })
      setAtBottom(true)
      endRef.current?.scrollIntoView({ block: 'end' })
    } catch (e) {
      if (e instanceof ApiError && e.code === 'version_conflict') setStale(true)
      else setError(e instanceof ApiError ? e.error.message : 'Sending failed. Your text is kept.')
      throw e
    }
  }

  const stop = async () => {
    if (!activeRunId) return
    try {
      const r = await unwrap(
        api.POST('/api/v1/runs/{run_id}/cancel', { params: { path: { run_id: activeRunId } } }),
      )
      qc.setQueryData(keys.run(r.id), r)
    } catch (e) {
      notify(
        e instanceof ApiError ? e.error.message : 'Stop did not reach the server. Try again.',
        'error',
      )
    }
  }

  const retry = async () => {
    if (!s || !latestRunId) return
    try {
      const r = await unwrap(
        api.POST('/api/v1/runs/{run_id}/retry', {
          params: {
            path: { run_id: latestRunId },
            header: { 'Idempotency-Key': newIdempotencyKey() },
          },
          body: { expected_version: s.version },
        }),
      )
      qc.setQueryData(keys.run(r.id), r)
      await qc.invalidateQueries({ queryKey: keys.session(id) })
    } catch (e) {
      notify(e instanceof ApiError ? e.error.message : 'Retry failed.', 'error')
      await qc.invalidateQueries({ queryKey: keys.session(id) })
    }
  }

  const summarize = () => {
    useRoomUi.getState().closeDrawer()
    void send(
      'Summarize where we are.',
      {
        audience: 'summary',
        target_persona_id: null,
        move_override: null,
        reply_to_message_id: null,
        idea_card_ids: [],
        research_override: 'off',
      },
      `summary:${id}`,
    ).catch(() => {})
  }

  // Roster changes run one at a time with the latest version, so quick toggles never race (M1).
  const selectionChain = useRef(Promise.resolve())
  const changeSelection = (ids: string[]) => {
    const current = qc.getQueryData<Schemas['Session']>(keys.session(id))
    if (current)
      qc.setQueryData(keys.session(id), { ...current, selected_persona_ids: ids as never })
    selectionChain.current = selectionChain.current.then(async () => {
      const latest = qc.getQueryData<Schemas['Session']>(keys.session(id))
      if (!latest) return
      try {
        const next = await unwrap(
          api.PATCH('/api/v1/sessions/{session_id}', {
            params: { path: { session_id: id } },
            body: { expected_version: latest.version, selected_persona_ids: ids as never },
          }),
        )
        qc.setQueryData(keys.session(id), next)
      } catch (e) {
        notify(e instanceof ApiError ? e.error.message : 'The selection was not saved.', 'error')
        await qc.invalidateQueries({ queryKey: keys.session(id) }) // show what the server has
      }
    })
  }

  const addConstraint = async () => {
    if (!s) return
    const text = await dialogs.prompt({
      title: 'Add a constraint',
      label: 'Constraint for this chat (saved to the brief)',
      confirmLabel: 'Add to brief',
      maxLength: 500,
    })
    if (text)
      await patchBrief(qc, s, {
        idea: s.brief.idea,
        goal: s.brief.goal,
        constraints: [...s.brief.constraints, text],
      })
  }

  const forkChat = async () => {
    if (!s) return
    const mode = await dialogs.choose({
      title: 'Fork this chat',
      body: 'Copies the whole conversation into a new chat. Choose how future turns run there.',
      options: [
        { value: 'jev_guided', label: 'Jev-guided' },
        { value: 'fixed_panel', label: 'Fixed panel' },
        { value: 'standard', label: 'Standard (one assistant)' },
      ],
      initial: s.mode,
      confirmLabel: 'Create fork',
    })
    if (mode) await actions.forkHere(null, mode as Schemas['Session']['mode'])
  }

  if (session.isError) {
    const gone = session.error instanceof ApiError && session.error.status === 404
    return (
      <section className="mx-auto max-w-[var(--layout-workspace-max)] px-4 py-10 sm:px-6 lg:px-12">
        <h1 className="text-[length:var(--text-title)] font-semibold">
          {gone ? 'This chat no longer exists' : 'This chat could not load'}
        </h1>
        <p className="mt-2 text-muted">
          {gone ? 'It may have been deleted. ' : `${session.error.message} `}
          <Link to="/chats" className="underline">
            Open all chats
          </Link>
        </p>
      </section>
    )
  }
  if (!s || !personas.data) return <p className="p-8 text-muted">Loading chat…</p>

  const standard = s.mode === 'standard'
  const disabledReason = s.is_archived
    ? 'This chat is archived. Restore it to continue.'
    : running
      ? 'Participants and settings can change after the current reply finishes.'
      : null
  const folderName = s.folder_id ? folders.data?.find((f) => f.id === s.folder_id)?.name : null
  const lr = latestRun.data
  const canRetry =
    !running && !s.is_archived && lr && RETRYABLE.includes(lr.status) && lr.id === lastUser?.run_id
  const notes = (lr?.warning_codes ?? []).filter((w) => w !== 'demo_mode')
  const summary = [...items].reverse().find((m) => m.summary)
  const replyLabel = (mid: string) => {
    const m = items.find((x) => x.id === mid)
    if (!m) return 'Replying to an earlier message'
    return `Replying to ${m.persona_id ? shortLabel(m.persona_id) : m.role === 'user' ? 'your message' : 'the moderator'}: “${(m.contribution?.headline ?? m.text ?? 'Summary').slice(0, 48)}”`
  }

  return (
    <RoomContext.Provider
      value={{ session: s, names, sources: sourceMap, saved, actions, running }}
    >
      <HeaderActions>
        <button
          type="button"
          onClick={() => useRoomUi.getState().openDrawer('ideas')}
          className="inline-flex min-h-10 items-center gap-2 rounded-control px-2 text-muted hover:text-text"
        >
          <Bookmark aria-hidden size={18} />
          <span className="max-md:sr-only">Saved ideas</span>
          {(ideas.data?.items.length ?? 0) > 0 && (
            <span className="text-[13px]">({ideas.data!.items.length})</span>
          )}
        </button>
        <RoomSettings session={s} disabled={disabledReason} />
        <DropdownMenu.Root>
          <DropdownMenu.Trigger
            aria-label="Chat options"
            className="grid size-10 place-items-center rounded-control border border-border text-muted hover:text-text"
          >
            <MoreHorizontal aria-hidden size={18} />
          </DropdownMenu.Trigger>
          <DropdownMenu.Portal>
            <DropdownMenu.Content align="end" sideOffset={4} className={menuContent}>
              <MenuItem onSelect={() => useRoomUi.getState().openDrawer('brief')}>Brief</MenuItem>
              <MenuItem onSelect={() => useRoomUi.getState().openDrawer('sources')}>
                Sources
              </MenuItem>
              <MenuItem
                disabled={running || s.is_archived || items.length === 0}
                onSelect={summarize}
              >
                Summarize
              </MenuItem>
              <MenuItem onSelect={() => useRoomUi.getState().openDrawer('run')}>
                Run details
              </MenuItem>
              <MenuItem
                disabled={running || s.is_archived || items.length === 0}
                onSelect={() => void forkChat()}
              >
                Fork chat…
              </MenuItem>
              <MenuItem onSelect={() => void exportChat(s, 'markdown')}>
                Export as Markdown
              </MenuItem>
              <MenuItem onSelect={() => void exportChat(s, 'json')}>Export as JSON</MenuItem>
              <DropdownMenu.Separator className="my-1 h-px bg-border" />
              <DropdownMenu.Sub>
                <DropdownMenu.SubTrigger className="flex min-h-10 cursor-pointer items-center rounded-control px-3 outline-none data-[highlighted]:bg-surface-subtle">
                  Organize…
                </DropdownMenu.SubTrigger>
                <DropdownMenu.Portal>
                  <DropdownMenu.SubContent className={menuContent}>
                    <ChatMenuItems
                      chat={{ ...s, active_run_id: activeRunId }}
                      onDeleted={() => (window.location.href = '/')}
                    />
                  </DropdownMenu.SubContent>
                </DropdownMenu.Portal>
              </DropdownMenu.Sub>
            </DropdownMenu.Content>
          </DropdownMenu.Portal>
        </DropdownMenu.Root>
      </HeaderActions>
      <section className="relative mx-auto flex min-h-full max-w-[var(--layout-workspace-max)] flex-col px-4 pt-6 sm:px-6 lg:px-12">
        <Doodles className="absolute top-4 right-6 w-56 lg:right-12" />
        <nav aria-label="Breadcrumb" className="text-[13px] text-muted">
          {s.folder_id ? (
            <Link to={`/folders/${s.folder_id}`} className="hover:underline">
              {folderName ?? 'Folder'}
            </Link>
          ) : (
            <Link to="/chats" className="hover:underline">
              No folder
            </Link>
          )}
          <span className="mx-2" aria-hidden>
            /
          </span>
          <span>{MODE_LABEL[s.mode]}</span>
          {s.origin_session_id && (
            <>
              <span className="mx-2" aria-hidden>
                /
              </span>
              <Link to={`/rooms/${s.origin_session_id}`} className="hover:underline">
                Branched from another chat
              </Link>
            </>
          )}
        </nav>
        <h1 className="mt-1 max-w-[30ch] text-[length:var(--text-title)] leading-tight font-semibold [overflow-wrap:anywhere] sm:text-[40px]">
          {s.title}
        </h1>
        {s.is_archived && (
          <div
            role="status"
            className="mt-4 flex flex-wrap items-center gap-3 rounded-card border border-border bg-surface-subtle p-3"
          >
            <span>
              This chat is archived. It stays readable and exportable; restore it to continue.
            </span>
            <button
              type="button"
              className="min-h-10 rounded-control bg-accent px-3 font-medium text-on-accent"
              onClick={() => void organize(qc, s, { is_archived: false })}
            >
              Restore
            </button>
          </div>
        )}
        <PersonaRoster
          selected={s.selected_persona_ids}
          personas={personas.data.items}
          defaultSelection={personas.data.default_selection}
          onChange={changeSelection}
          disabledReason={disabledReason}
          onAskDirectly={(pid) => void actions.target(pid)}
          standard={standard}
        />
        {messages.data?.previous_cursor && (
          <button
            type="button"
            onClick={() => void loadPage('older')}
            className="mt-6 self-center rounded-control border border-border px-4 py-2 text-[14px] hover:bg-surface-subtle"
          >
            Load earlier messages
          </button>
        )}
        <div className="mt-8 flex flex-1 flex-col gap-10" aria-label="Conversation">
          {messages.isPending && <p className="text-muted">Loading conversation…</p>}
          {messages.isSuccess && items.length === 0 && (
            <p className="text-muted">
              No messages yet. Bring the first thought to the room below.
            </p>
          )}
          {groups.map((g, i) => (
            <TurnGroup
              key={g.key}
              group={g}
              first={i === 0 && !messages.data?.previous_cursor}
              footer={
                i === groups.length - 1 ? (
                  <div className="flex flex-col gap-2">
                    {(activeRun.data ?? lr) &&
                      (running || (lr && RETRYABLE.includes(lr.status))) && (
                        <RunSlots run={(running ? activeRun.data : lr)!} events={events} />
                      )}
                    {!running && notes.length > 0 && (
                      <ul className="text-[14px] text-muted">
                        {notes.map((w) => (
                          <li key={w}>{warningText(w)}</li>
                        ))}
                      </ul>
                    )}
                    {canRetry && (
                      <button
                        type="button"
                        onClick={() => void retry()}
                        className="inline-flex min-h-10 items-center gap-2 self-start rounded-control border border-border px-3 hover:bg-surface-subtle"
                      >
                        <RotateCcw aria-hidden size={16} /> Retry missing replies
                      </button>
                    )}
                  </div>
                ) : undefined
              }
            />
          ))}
          {messages.data?.next_cursor && (
            <button
              type="button"
              onClick={() => void loadPage('newer')}
              className="self-center rounded-control border border-border px-4 py-2 text-[14px] hover:bg-surface-subtle"
            >
              Load newer messages
            </button>
          )}
          <div ref={endRef} />
        </div>
        {unseen && (
          <button
            type="button"
            onClick={() => {
              endRef.current?.scrollIntoView({ block: 'end', behavior: 'smooth' })
              setUnseen(false)
            }}
            className="sticky bottom-28 z-20 mx-auto inline-flex min-h-10 items-center gap-2 rounded-full bg-accent px-4 font-medium text-on-accent shadow-lg"
          >
            <ArrowDown aria-hidden size={16} /> New responses
          </button>
        )}
        {(error || stale) && (
          <div role="alert" className="mt-4 rounded-card border border-danger p-3 text-[15px]">
            {stale ? (
              <>
                This chat changed in another tab or by a finished reply. Your text is kept.{' '}
                <button
                  type="button"
                  className="underline"
                  onClick={async () => {
                    await qc.invalidateQueries({ queryKey: keys.session(id) })
                    await qc.invalidateQueries({ queryKey: keys.messages(id) })
                    setStale(false)
                  }}
                >
                  Refresh, then send again
                </button>
              </>
            ) : (
              error
            )}
          </div>
        )}
        {!s.is_archived && (
          <Composer
            draftKey={id}
            personas={personas.data.items}
            selected={s.selected_persona_ids}
            standard={standard}
            running={running}
            disabledReason={null}
            ideas={ideas.data?.items ?? []}
            replyLabel={replyLabel}
            onSend={send}
            onStop={() => void stop()}
            onTarget={actions.target}
            onAddConstraint={running ? undefined : () => void addConstraint()}
            registerFocus={registerFocus}
          />
        )}
        <p className="pb-4 text-center text-[13px] text-muted">
          AI perspectives · Different views, one conversation
        </p>
      </section>
      <DetailsDrawer
        session={s}
        ideas={ideas.data?.items ?? []}
        sources={sources.data ?? []}
        summary={summary}
        latestRunId={latestRunId}
        running={running}
        onSummarize={summarize}
      />
    </RoomContext.Provider>
  )
}

/** One RoomPage per chat: switching chats never carries errors, scroll state or pills over. */
export function RoomRoute() {
  const { id = '' } = useParams()
  return <RoomPage key={id} />
}
