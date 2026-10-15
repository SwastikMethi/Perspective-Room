import { useQueryClient } from '@tanstack/react-query'
import { ExternalLink, X } from 'lucide-react'
import { Dialog, Tabs } from 'radix-ui'
import { useEffect, useState } from 'react'
import { ApiError, api, type Schemas, unwrap } from '../../api/client'
import { keys, useRun } from '../../api/queries'
import { dialogs, notify, primaryButton, secondaryButton } from '../../components/Dialogs'
import { useReturnFocus } from '../../components/focus'
import { safeUrl } from '../../components/MarkdownText'
import { useDrafts } from '../../stores/drafts'
import { SECTION_LABELS, warningText } from './copy'
import { type DrawerTab, STAGE_TEXT, useRoomUi } from './roomUi'

const TABS: { value: DrawerTab; label: string }[] = [
  { value: 'brief', label: 'Brief' },
  { value: 'ideas', label: 'Saved ideas' },
  { value: 'sources', label: 'Sources' },
  { value: 'summary', label: 'Summary' },
  { value: 'run', label: 'Run details' },
]

const errorText = (e: unknown) => (e instanceof ApiError ? e.error.message : 'That did not work.')
const field = 'mt-1 w-full rounded-control border border-border bg-canvas px-3 py-2 text-text'

export async function patchBrief(
  qc: ReturnType<typeof useQueryClient>,
  session: Schemas['Session'],
  brief: { idea: string; goal: string | null; constraints: string[] },
): Promise<boolean> {
  try {
    const next = await unwrap(
      api.PATCH('/api/v1/sessions/{session_id}', {
        params: { path: { session_id: session.id } },
        body: { expected_version: session.version, brief },
      }),
    )
    qc.setQueryData(keys.session(session.id), next)
    notify(`Brief updated — revision ${next.brief.revision}. The next turn uses it.`)
    return true
  } catch (e) {
    notify(
      e instanceof ApiError && e.code === 'version_conflict'
        ? 'This chat changed; refresh to see the latest brief, then reapply your edit.'
        : errorText(e),
      'error',
    )
    await qc.invalidateQueries({ queryKey: keys.session(session.id) })
    return false
  }
}

function BriefTab({
  session,
  summary,
  running,
}: {
  session: Schemas['Session']
  summary: Schemas['Message'] | undefined
  running: boolean
}) {
  const qc = useQueryClient()
  const b = session.brief
  const [editing, setEditing] = useState(false)
  const [idea, setIdea] = useState(b.idea)
  const [goal, setGoal] = useState(b.goal ?? '')
  const [constraints, setConstraints] = useState(b.constraints.join('\n'))
  useEffect(() => {
    setIdea(b.idea)
    setGoal(b.goal ?? '')
    setConstraints(b.constraints.join('\n'))
  }, [b])
  const locked = running || session.is_archived
  const suggested =
    summary?.summary?.sections
      .filter((s) => s.kind === 'assumptions' || s.kind === 'questions')
      .flatMap((s) =>
        s.items
          .filter((i) => i.source_message_ids.length > 0)
          .map((i) => ({ kind: s.kind, text: i.text })),
      ) ?? []
  return (
    <div>
      <p className="text-[13px] text-muted">Confirmed by you · revision {b.revision}</p>
      {!editing ? (
        <>
          <h3 className="mt-2 font-semibold">Idea</h3>
          <p className="whitespace-pre-wrap [overflow-wrap:anywhere]">{b.idea}</p>
          <h3 className="mt-3 font-semibold">Goal</h3>
          <p className="text-muted">{b.goal || 'No goal set.'}</p>
          <h3 className="mt-3 font-semibold">Constraints</h3>
          {b.constraints.length ? (
            <ul className="list-disc pl-5">
              {b.constraints.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
          ) : (
            <p className="text-muted">No constraints yet.</p>
          )}
          <button
            type="button"
            disabled={locked}
            onClick={() => setEditing(true)}
            className={secondaryButton + ' mt-4'}
          >
            Edit brief
          </button>
          {locked && (
            <p className="mt-1 text-[13px] text-muted">
              {session.is_archived
                ? 'Restore the chat to edit its brief.'
                : 'Edit after the current reply finishes.'}
            </p>
          )}
        </>
      ) : (
        <form
          className="mt-2"
          onSubmit={async (e) => {
            e.preventDefault()
            const ok = await patchBrief(qc, session, {
              idea: idea.trim(),
              goal: goal.trim() || null,
              constraints: constraints
                .split('\n')
                .map((c) => c.trim())
                .filter(Boolean),
            })
            if (ok) setEditing(false)
          }}
        >
          <label className="block text-[13px] text-muted" htmlFor="brief-idea">
            Idea
          </label>
          <textarea
            id="brief-idea"
            className={field}
            rows={3}
            value={idea}
            maxLength={16000}
            onChange={(e) => setIdea(e.target.value)}
          />
          <label className="mt-2 block text-[13px] text-muted" htmlFor="brief-goal">
            Goal
          </label>
          <input
            id="brief-goal"
            className={field}
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
          />
          <label className="mt-2 block text-[13px] text-muted" htmlFor="brief-constraints">
            Constraints, one per line
          </label>
          <textarea
            id="brief-constraints"
            className={field}
            rows={4}
            value={constraints}
            onChange={(e) => setConstraints(e.target.value)}
          />
          <div className="mt-3 flex gap-2">
            <button type="submit" disabled={!idea.trim()} className={primaryButton}>
              Save as new revision
            </button>
            <button type="button" className={secondaryButton} onClick={() => setEditing(false)}>
              Cancel
            </button>
          </div>
        </form>
      )}
      {suggested.length > 0 && (
        <div className="mt-6 border-t border-border pt-4">
          <h3 className="font-semibold">Suggested by the conversation</h3>
          <p className="text-[13px] text-muted">
            Not confirmed. Add one to the brief only if it is right.
          </p>
          <ul className="mt-2 space-y-2">
            {suggested.map((s) => (
              <li
                key={s.text}
                className="rounded-control border border-dashed border-border p-2 text-[14px]"
              >
                <span className="text-[12px] text-muted">
                  {s.kind === 'questions' ? 'Open question' : 'Assumption'} · suggested
                </span>
                <p>{s.text}</p>
                <button
                  type="button"
                  disabled={locked || b.constraints.includes(s.text)}
                  onClick={() =>
                    void patchBrief(qc, session, {
                      idea: b.idea,
                      goal: b.goal,
                      constraints: [...b.constraints, s.text],
                    })
                  }
                  className="mt-1 text-[13px] underline disabled:opacity-60"
                >
                  {b.constraints.includes(s.text) ? 'In the brief' : 'Add to brief'}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

function IdeaRow({
  card,
  picked,
  onPick,
  locked,
}: {
  card: Schemas['IdeaCard']
  picked: boolean
  onPick: (on: boolean) => void
  locked: boolean
}) {
  const qc = useQueryClient()
  const [note, setNote] = useState(card.note)
  useEffect(() => setNote(card.note), [card.note])
  const save = async (patch: Partial<Pick<Schemas['IdeaCard'], 'note' | 'status' | 'title'>>) => {
    try {
      await unwrap(
        api.PATCH('/api/v1/idea-cards/{card_id}', {
          params: { path: { card_id: card.id } },
          body: { expected_version: card.version, ...patch },
        }),
      )
    } catch (e) {
      notify(errorText(e), 'error')
    } finally {
      await qc.invalidateQueries({ queryKey: keys.ideas(card.session_id) })
    }
  }
  return (
    <li className="rounded-card border border-border p-3">
      <label className="flex items-start gap-2">
        <input
          type="checkbox"
          checked={picked}
          disabled={locked}
          onChange={(e) => onPick(e.target.checked)}
          className="mt-1 size-4 accent-[var(--accent)]"
        />
        <span className="font-medium [overflow-wrap:anywhere]">{card.title}</span>
      </label>
      <label className="mt-2 block text-[13px] text-muted" htmlFor={`note-${card.id}`}>
        Note
      </label>
      <textarea
        id={`note-${card.id}`}
        className={field}
        rows={2}
        value={note}
        disabled={locked}
        maxLength={4000}
        onChange={(e) => setNote(e.target.value)}
        onBlur={() => note !== card.note && void save({ note })}
      />
      <div className="mt-2 flex items-center gap-2">
        <label className="text-[13px] text-muted" htmlFor={`status-${card.id}`}>
          Status
        </label>
        <select
          id={`status-${card.id}`}
          value={card.status}
          disabled={locked}
          onChange={(e) => void save({ status: e.target.value as Schemas['IdeaCard']['status'] })}
          className="min-h-9 rounded-control border border-border bg-surface px-2 text-[14px]"
        >
          <option value="exploring">Exploring</option>
          <option value="selected">Selected</option>
          <option value="parked">Parked</option>
        </select>
        <button
          type="button"
          disabled={locked}
          className="ml-auto text-[13px] text-danger underline"
          onClick={async () => {
            const sure =
              !card.note.trim() ||
              (await dialogs.confirm({
                title: 'Remove this saved idea?',
                body: 'Its note will be removed too.',
                confirmLabel: 'Remove',
                danger: true,
              }))
            if (!sure) return
            try {
              await unwrap(
                api.DELETE('/api/v1/idea-cards/{card_id}', {
                  params: { path: { card_id: card.id } },
                }),
              )
            } catch (e) {
              notify(errorText(e), 'error')
            }
            await qc.invalidateQueries({ queryKey: keys.ideas(card.session_id) })
          }}
        >
          Remove
        </button>
      </div>
    </li>
  )
}

function IdeasTab({
  sessionId,
  ideas,
  locked,
}: {
  sessionId: string
  ideas: Schemas['IdeaCard'][]
  locked: boolean
}) {
  const [picked, setPicked] = useState<string[]>([])
  if (!ideas.length)
    return (
      <p className="text-muted">No saved ideas yet. Use the bookmark on a reply to keep it here.</p>
    )
  return (
    <div>
      <ul className="space-y-3">
        {ideas.map((c) => (
          <IdeaRow
            key={c.id}
            card={c}
            locked={locked}
            picked={picked.includes(c.id)}
            onPick={(on) => setPicked((p) => (on ? [...p, c.id] : p.filter((x) => x !== c.id)))}
          />
        ))}
      </ul>
      <button
        type="button"
        disabled={locked || picked.length < 2}
        className={primaryButton + ' mt-4'}
        onClick={() => {
          const current = useDrafts.getState().get(sessionId)?.control ?? {}
          useDrafts.getState().set(sessionId, {
            control: { ...current, move_override: 'combine', idea_card_ids: picked },
          })
          useRoomUi.getState().closeDrawer()
          setTimeout(() => useRoomUi.getState().focusComposer(), 50)
        }}
      >
        Combine selected ({picked.length})
      </button>
      {picked.length < 2 && (
        <p className="mt-1 text-[13px] text-muted">Pick at least two ideas to combine.</p>
      )}
    </div>
  )
}

function SourcesTab({ sources, focus }: { sources: Schemas['Source'][]; focus?: string }) {
  useEffect(() => {
    if (focus) document.getElementById(`source-${focus}`)?.scrollIntoView({ block: 'nearest' })
  }, [focus])
  if (!sources.length)
    return (
      <p className="text-muted">
        No sources yet. Research runs when a turn needs current facts, or when you set Research:
        Force.
      </p>
    )
  return (
    <ol className="space-y-3">
      {sources.map((s) => {
        const url = safeUrl(s.url)
        return (
          <li
            key={s.id}
            id={`source-${s.id}`}
            tabIndex={-1}
            className={
              'rounded-card border p-3 ' +
              (s.id === focus
                ? 'border-selection-border ring-2 ring-selection-border'
                : 'border-border')
            }
          >
            <p className="font-medium [overflow-wrap:anywhere]">{s.title}</p>
            <p className="text-[13px] text-muted">
              {s.domain} · retrieved {new Date(s.retrieved_at).toLocaleDateString()}
              {s.published_at
                ? ` · published ${new Date(s.published_at).toLocaleDateString()}`
                : ''}
              {s.is_fixture ? ' · demo fixture, not live research' : ''}
            </p>
            {s.research_excerpt && (
              <blockquote className="mt-2 border-l-2 border-border pl-3 text-[14px] [overflow-wrap:anywhere]">
                {s.research_excerpt}
              </blockquote>
            )}
            {url && (
              <a
                href={url}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-2 inline-flex min-h-9 items-center gap-1 text-[14px] underline"
              >
                Open source <ExternalLink aria-hidden size={14} />
                <span className="sr-only">(opens in a new tab)</span>
              </a>
            )}
          </li>
        )
      })}
    </ol>
  )
}

function SummaryTab({
  summary,
  onSummarize,
  locked,
}: {
  summary: Schemas['Message'] | undefined
  onSummarize: () => void
  locked: boolean
}) {
  if (!summary?.summary)
    return (
      <div>
        <p className="text-muted">
          No summary yet. A summary collects directions, disagreements, assumptions, open questions
          and experiments from this chat.
        </p>
        <button
          type="button"
          disabled={locked}
          onClick={onSummarize}
          className={primaryButton + ' mt-3'}
        >
          Summarize now
        </button>
      </div>
    )
  return (
    <div className="space-y-4">
      {summary.summary.sections.map((s) => (
        <section key={s.kind}>
          <h3 className="font-semibold">{SECTION_LABELS[s.kind]}</h3>
          <ul className="mt-1 list-disc pl-5 text-[15px]">
            {s.items.map((i, n) => (
              <li key={n}>
                {i.text}
                {i.source_ids.map((id) => (
                  <button
                    key={id}
                    type="button"
                    onClick={() => useRoomUi.getState().openDrawer('sources', id)}
                    className="ml-1 text-[12px] underline"
                  >
                    source
                  </button>
                ))}
                {i.source_message_ids.map((id) => (
                  <a
                    key={id}
                    href={`#m-${id}`}
                    onClick={() => {
                      useRoomUi.setState({ highlight: id })
                      useRoomUi.getState().closeDrawer()
                    }}
                    className="ml-1 text-[12px] text-muted underline"
                  >
                    reply
                  </a>
                ))}
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  )
}

function RunTab({ runId }: { runId: string | null }) {
  const run = useRun(runId)
  if (!runId) return <p className="text-muted">No turn has run in this chat yet.</p>
  if (!run.data) return <p className="text-muted">Loading run details…</p>
  const r = run.data
  const u = r.usage
  const warnings = r.warning_codes
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-[15px]">
      <dt className="text-muted">Status</dt>
      <dd>{r.status}</dd>
      <dt className="text-muted">Stage</dt>
      <dd>{STAGE_TEXT[r.stage] ?? r.stage}</dd>
      <dt className="text-muted">Replies</dt>
      <dd>
        {r.published_count} of {r.requested_count} requested
      </dd>
      <dt className="text-muted">Quality</dt>
      <dd>
        {r.degraded ? 'Degraded — a fallback or check was used (see notes).' : 'No fallback used.'}
      </dd>
      <dt className="text-muted">Notes</dt>
      <dd>
        {warnings.length ? (
          <ul className="list-disc pl-5">
            {warnings.map((w) => (
              <li key={w}>{warningText(w)}</li>
            ))}
          </ul>
        ) : (
          'None'
        )}
      </dd>
      {r.error && (
        <>
          <dt className="text-muted">Error</dt>
          <dd>{r.error.message}</dd>
        </>
      )}
      <dt className="text-muted">Usage</dt>
      <dd>
        {u.input_tokens == null && u.output_tokens == null
          ? 'Unknown'
          : `${u.input_tokens ?? '?'} input · ${u.output_tokens ?? '?'} output tokens${u.usage_incomplete ? ' (incomplete)' : ''}`}
      </dd>
      <dt className="text-muted">Cost</dt>
      <dd>
        {u.estimated_cost_usd == null
          ? 'Unknown — no rate card is configured'
          : `$${u.estimated_cost_usd.toFixed(4)}`}
      </dd>
    </dl>
  )
}

export function DetailsDrawer({
  session,
  ideas,
  sources,
  summary,
  latestRunId,
  running,
  onSummarize,
}: {
  session: Schemas['Session']
  ideas: Schemas['IdeaCard'][]
  sources: Schemas['Source'][]
  summary: Schemas['Message'] | undefined
  latestRunId: string | null
  running: boolean
  onSummarize: () => void
}) {
  const drawer = useRoomUi((s) => s.drawer)
  const open = useRoomUi((s) => s.openDrawer)
  const close = useRoomUi((s) => s.closeDrawer)
  const locked = running || session.is_archived
  const returnFocus = useReturnFocus(Boolean(drawer))
  return (
    <Dialog.Root open={Boolean(drawer)} onOpenChange={(o) => !o && close()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/30" />
        <Dialog.Content
          onCloseAutoFocus={returnFocus}
          className="fixed inset-y-0 right-0 z-50 flex w-full flex-col border-l border-border bg-surface text-text shadow-xl sm:w-[var(--layout-details-drawer)]"
        >
          <div className="flex items-center justify-between border-b border-border px-4 py-3">
            <Dialog.Title className="text-[17px] font-semibold">Chat details</Dialog.Title>
            <Dialog.Description className="sr-only">
              Brief, saved ideas, sources, summary and run details for this chat
            </Dialog.Description>
            <Dialog.Close
              aria-label="Close details"
              className="grid size-10 place-items-center rounded-control text-muted hover:text-text"
            >
              <X aria-hidden size={20} />
            </Dialog.Close>
          </div>
          <Tabs.Root
            value={drawer?.tab ?? 'brief'}
            onValueChange={(v) => open(v as DrawerTab)}
            className="flex min-h-0 flex-1 flex-col"
          >
            <Tabs.List
              aria-label="Details"
              className="flex gap-0.5 overflow-x-auto border-b border-border px-1"
            >
              {TABS.map((t) => (
                <Tabs.Trigger
                  key={t.value}
                  value={t.value}
                  className="min-h-11 shrink-0 border-b-2 border-transparent px-2 text-[13px] text-muted data-[state=active]:border-selection-border data-[state=active]:font-medium data-[state=active]:text-text"
                >
                  {t.label}
                  {t.value === 'ideas' && ideas.length > 0 ? ` (${ideas.length})` : ''}
                  {t.value === 'sources' && sources.length > 0 ? ` (${sources.length})` : ''}
                </Tabs.Trigger>
              ))}
            </Tabs.List>
            <div className="min-h-0 flex-1 overflow-y-auto p-4 [overflow-wrap:anywhere]">
              <Tabs.Content value="brief">
                <BriefTab session={session} summary={summary} running={running} />
              </Tabs.Content>
              <Tabs.Content value="ideas">
                <IdeasTab sessionId={session.id} ideas={ideas} locked={locked} />
              </Tabs.Content>
              <Tabs.Content value="sources">
                <SourcesTab sources={sources} focus={drawer?.sourceId} />
              </Tabs.Content>
              <Tabs.Content value="summary">
                <SummaryTab summary={summary} onSummarize={onSummarize} locked={locked} />
              </Tabs.Content>
              <Tabs.Content value="run">
                <RunTab runId={latestRunId} />
              </Tabs.Content>
            </div>
          </Tabs.Root>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
