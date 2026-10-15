import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { api, ApiError, newIdempotencyKey, type Schemas, unwrap } from '../../api/client'
import { dialogs, notify, primaryButton, secondaryButton } from '../../components/Dialogs'
import { shortLabel } from '../../lib/personas'
import { safeStorage } from '../../stores/safeStorage'

const RUBRIC = {
  useful_breadth: [
    'Useful breadth',
    'Repeats one view or irrelevant alternatives',
    'Several relevant angles with some overlap',
    'Distinct, useful possibilities that change what you could consider',
  ],
  usefulness: [
    'Usefulness',
    'Generic or hard to act on',
    'Some concrete suggestions',
    'Clear, relevant next steps tailored to the constraints',
  ],
  consistency: [
    'Personality consistency',
    'Mostly indistinguishable or contradictory',
    'Recognizable profiles with drift',
    'Stable priorities with sensible updates',
  ],
  redundancy: [
    'Redundancy (lower is better)',
    'Little unnecessary repetition',
    'Several overlapping contributions',
    'Mostly repetition without development',
  ],
} as const
type Metric = keyof typeof RUBRIC
const LABELS = [
  ['unsupported_claim', 'Unsupported factual claim'],
  ['missed_constraint', 'Missed an explicit constraint'],
  ['false_credential', 'Claimed a false credential'],
  ['mishandled_disagreement', 'Mishandled disagreement'],
] as const
const ALIAS_KEY = 'perspective-room:lab:v1'
const MODE = { standard: 'Standard', fixed_panel: 'Fixed panel', jev_guided: 'Jev-guided' }

function Scale({
  metric,
  value,
  onChange,
  name,
}: {
  metric: Metric
  value: number | null
  onChange: (v: number) => void
  name: string
}) {
  const [label, low, mid, high] = RUBRIC[metric]
  return (
    <fieldset className="mt-3">
      <legend className="font-medium">{label}</legend>
      <div className="mt-1 flex flex-wrap gap-1">
        {[1, 2, 3, 4, 5].map((n) => (
          <label
            key={n}
            className="flex min-h-10 min-w-10 cursor-pointer items-center justify-center gap-1 rounded-control border border-border px-2 has-[:checked]:border-selection-border has-[:checked]:bg-selection-surface"
          >
            <input
              type="radio"
              name={name}
              value={n}
              checked={value === n}
              onChange={() => onChange(n)}
              className="sr-only"
            />
            {n}
          </label>
        ))}
      </div>
      <p className="mt-1 text-[12px] text-muted">
        1 — {low} · 3 — {mid} · 5 — {high}
      </p>
    </fieldset>
  )
}

function Transcript({ trial }: { trial: Schemas['Trial'] }) {
  return (
    <ol className="max-h-[28rem] space-y-2 overflow-y-auto rounded-control border border-border bg-canvas p-3 text-[14px]">
      {trial.messages.map((m) => (
        <li key={m.id} className="[overflow-wrap:anywhere]">
          {m.role === 'user' ? (
            <p>
              <strong>Turn:</strong> {m.text}
            </p>
          ) : m.contribution ? (
            <div>
              <p className="font-medium">
                {m.persona_id ? shortLabel(m.persona_id) : 'Assistant'} — {m.contribution.headline}
              </p>
              {m.contribution.blocks.map((b, i) => (
                <p key={i} className="text-muted">
                  {b.text}
                </p>
              ))}
            </div>
          ) : (
            <p className="text-muted">{m.text ?? 'Summary'}</p>
          )}
        </li>
      ))}
      {trial.messages.length === 0 && <li className="text-muted">No output yet.</li>}
    </ol>
  )
}

function RatingForm({
  batchId,
  trial,
  alias,
  onSaved,
}: {
  batchId: string
  trial: Schemas['Trial']
  alias: string
  onSaved: () => void
}) {
  const single = !trial.messages.some((m) => m.persona_id) // the speaker count is visible anyway
  const [scores, setScores] = useState<Record<Metric, number | null>>({
    useful_breadth: null,
    usefulness: null,
    consistency: null,
    redundancy: null,
  })
  const [labels, setLabels] = useState<string[]>([])
  const [directions, setDirections] = useState('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const ready = alias.trim() && scores.useful_breadth && scores.usefulness && scores.redundancy
  return (
    <form
      className="mt-3"
      onSubmit={async (e) => {
        e.preventDefault()
        if (!ready) return
        setBusy(true)
        try {
          const r = await unwrap(
            api.POST('/api/v1/evaluations/{evaluation_id}/ratings', {
              params: {
                path: { evaluation_id: batchId },
                header: { 'Idempotency-Key': newIdempotencyKey() },
              },
              body: {
                trial_id: trial.id,
                rater_alias: alias.trim(),
                useful_breadth: scores.useful_breadth!,
                usefulness: scores.usefulness!,
                consistency: single ? null : scores.consistency,
                redundancy: scores.redundancy!,
                note,
                unblinded: false,
                labels: labels as Schemas['RatingCreate']['labels'],
                distinct_directions: directions === '' ? null : Number(directions),
              },
            }),
          )
          notify(
            `Rating saved for ${trial.blind_label}${r.unblinded ? ' (recorded as unblinded)' : ''}.`,
          )
          onSaved()
        } catch (err) {
          notify(err instanceof ApiError ? err.error.message : 'The rating was not saved.', 'error')
        } finally {
          setBusy(false)
        }
      }}
    >
      {(Object.keys(RUBRIC) as Metric[])
        .filter((m) => !(single && m === 'consistency'))
        .map((m) => (
          <Scale
            key={m}
            metric={m}
            name={`${trial.id}-${m}`}
            value={scores[m]}
            onChange={(v) => setScores((s) => ({ ...s, [m]: v }))}
          />
        ))}
      {single && (
        <p className="mt-2 text-[13px] text-muted">
          Personality consistency does not apply to a single assistant.
        </p>
      )}
      <fieldset className="mt-3">
        <legend className="font-medium">Problems noticed</legend>
        {LABELS.map(([value, text]) => (
          <label key={value} className="mt-1 flex min-h-9 items-center gap-2 text-[14px]">
            <input
              type="checkbox"
              checked={labels.includes(value)}
              onChange={(e) =>
                setLabels((l) => (e.target.checked ? [...l, value] : l.filter((x) => x !== value)))
              }
              className="size-4 accent-[var(--accent)]"
            />
            {text}
          </label>
        ))}
      </fieldset>
      <label className="mt-3 block text-[14px] font-medium" htmlFor={`dir-${trial.id}`}>
        Distinct useful directions (count by meaning)
      </label>
      <input
        id={`dir-${trial.id}`}
        type="number"
        min={0}
        value={directions}
        onChange={(e) => setDirections(e.target.value)}
        className="mt-1 w-24 rounded-control border border-border bg-canvas px-2 py-1.5"
      />
      <label className="mt-3 block text-[14px] font-medium" htmlFor={`note-${trial.id}`}>
        Note (optional)
      </label>
      <textarea
        id={`note-${trial.id}`}
        rows={2}
        maxLength={4000}
        value={note}
        onChange={(e) => setNote(e.target.value)}
        className="mt-1 w-full rounded-control border border-border bg-canvas p-2"
      />
      <button type="submit" disabled={!ready || busy} className={primaryButton + ' mt-3'}>
        {busy ? 'Saving…' : `Save rating for ${trial.blind_label}`}
      </button>
      {!alias.trim() && (
        <p className="mt-1 text-[13px] text-muted">Enter a rater alias above first.</p>
      )}
    </form>
  )
}

/** Blind rating (doc 09): neutral labels, no mode/metrics; reveal is explicit and recorded. */
export function RatingView({ batch }: { batch: Schemas['Evaluation'] }) {
  const qc = useQueryClient()
  const [revealed, setRevealed] = useState(false)
  const [alias, setAlias] = useState(() => String(safeStorage.getItem(ALIAS_KEY) ?? ''))
  const [saved, setSaved] = useState<Record<string, number>>({})
  const active = batch.status === 'queued' || batch.status === 'running'
  const trials = useQuery({
    queryKey: ['lab-trials', batch.id, revealed],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/evaluations/{evaluation_id}/trials', {
          params: { path: { evaluation_id: batch.id }, query: { limit: 100, reveal: revealed } },
        }),
      ),
    refetchOnWindowFocus: false, // never re-reveal or refetch behind the rater's back
    placeholderData: keepPreviousData, // revealing keeps the page (and unsaved inputs) in place
    refetchInterval: active ? 3000 : false,
  })
  // Pick up the final trial states when the batch's progress changes (polling stops at the end).
  const progress = `${batch.status}:${batch.finished_trials}:${batch.failed_trials}`
  const { refetch } = trials
  useEffect(() => {
    void refetch()
  }, [progress, refetch])
  const groups = new Map<string, Schemas['Trial'][]>()
  for (const t of trials.data?.items ?? []) {
    const key = `${t.case_id} · repetition ${t.replicate}`
    groups.set(key, [...(groups.get(key) ?? []), t])
  }
  return (
    <div>
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <label htmlFor="rater-alias" className="block text-[14px] font-medium">
            Rater alias
          </label>
          <input
            id="rater-alias"
            value={alias}
            maxLength={80}
            onChange={(e) => {
              setAlias(e.target.value)
              safeStorage.setItem(ALIAS_KEY, e.target.value) // memory fallback if blocked
            }}
            placeholder="e.g. rater-a (not your full name)"
            className="mt-1 w-64 rounded-control border border-border bg-canvas px-3 py-2"
          />
        </div>
        {!revealed && (
          <button
            type="button"
            className={secondaryButton}
            onClick={async () => {
              const ok = await dialogs.confirm({
                title: 'Reveal conditions?',
                body: 'Shows which output came from which condition and records the reveal. Ratings saved afterwards are marked unblinded.',
                confirmLabel: 'Reveal conditions',
              })
              if (ok) {
                setRevealed(true)
                await qc.invalidateQueries({ queryKey: ['lab-batch', batch.id] })
              }
            }}
          >
            Reveal conditions
          </button>
        )}
      </div>
      {trials.isPending && <p className="mt-4 text-muted">Loading outputs…</p>}
      {trials.isError && (
        <p role="alert" className="mt-4">
          Outputs could not load: {trials.error.message}
        </p>
      )}
      {[...groups].map(([key, list]) => (
        <section key={key} className="mt-6">
          <h3 className="text-[17px] font-semibold">{key}</h3>
          <div className="mt-2 grid gap-4 [grid-template-columns:repeat(auto-fit,minmax(min(100%,320px),1fr))]">
            {list.map((t) => (
              <article key={t.id} className="rounded-card border border-border bg-surface p-4">
                <header className="flex items-center justify-between gap-2">
                  <h4 className="font-semibold">{t.blind_label}</h4>
                  <span className="text-[13px] text-muted">
                    {t.status}
                    {t.mode ? ` · ${MODE[t.mode]}${t.degraded ? ' · degraded' : ''}` : ''}
                    {saved[t.id] ? ` · rated ×${saved[t.id]}` : ''}
                  </span>
                </header>
                <div className="mt-2">
                  <Transcript trial={t} />
                </div>
                {t.status === 'completed' || t.status === 'partial' ? (
                  <RatingForm
                    batchId={batch.id}
                    trial={t}
                    alias={alias}
                    onSaved={() => setSaved((s) => ({ ...s, [t.id]: (s[t.id] ?? 0) + 1 }))}
                  />
                ) : (
                  <p className="mt-2 text-[13px] text-muted">
                    {t.status === 'queued' || t.status === 'running'
                      ? 'Rate this output once it has finished.'
                      : `This trial ended ${t.status} without output to rate; results count it as incomplete.`}
                  </p>
                )}
              </article>
            ))}
          </div>
        </section>
      ))}
    </div>
  )
}
