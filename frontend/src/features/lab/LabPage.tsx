import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Tabs } from 'radix-ui'
import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router'
import { api, ApiError, newIdempotencyKey, type Schemas, unwrap } from '../../api/client'
import { useSettings } from '../../api/queries'
import { dialogs, notify, primaryButton, secondaryButton } from '../../components/Dialogs'
import { RatingView } from './RatingView'
import { ResultsView } from './ResultsView'

type Mode = Schemas['EvaluationCreate']['modes'][number]
const MODES: { value: Mode; label: string; hint: string }[] = [
  { value: 'standard', label: 'Standard (A)', hint: 'one neutral assistant' },
  { value: 'fixed_panel', label: 'Fixed panel (B)', hint: 'round-robin speakers, no Jev' },
  { value: 'jev_guided', label: 'Jev-guided (C)', hint: 'Jev picks speakers and checks fit' },
]
const EVIDENCE = [
  { value: 'off', label: 'Off', hint: 'no research — the primary comparison' },
  {
    value: 'fixture',
    label: 'Fixture',
    hint: 'the same labeled synthetic pack where a case names one',
  },
  {
    value: 'live',
    label: 'Live',
    hint: 'live search per condition — a separate end-to-end comparison',
  },
] as const
const MAX = 90

function NewBatch({ onCreated }: { onCreated: (id: string) => void }) {
  const settings = useSettings()
  const cases = useQuery({
    queryKey: ['lab-cases'],
    queryFn: () => unwrap(api.GET('/api/v1/evaluation-cases')),
    staleTime: Infinity,
  })
  const [domain, setDomain] = useState('all')
  const [picked, setPicked] = useState<string[]>([])
  const [modes, setModes] = useState<Mode[]>(['standard', 'fixed_panel', 'jev_guided'])
  const [reps, setReps] = useState(1)
  const [evidence, setEvidence] = useState<Schemas['EvaluationCreate']['evidence_policy']>('off')
  const [busy, setBusy] = useState(false)
  const domains = useMemo(() => [...new Set(cases.data?.items.map((c) => c.domain))], [cases.data])
  const shown = (cases.data?.items ?? []).filter((c) => domain === 'all' || c.domain === domain)
  const planned = picked.length * modes.length * reps
  const live = settings.data?.provider_mode !== 'demo' // unknown counts as live: confirm
  const run = async () => {
    if (live) {
      const ok = await dialogs.confirm({
        title: `Run ${planned} live trials?`,
        body: `Each trial is a full three-turn conversation with paid provider calls (about ${planned * 3} turns). Nothing runs until you confirm.`,
        confirmLabel: 'Run live batch',
      })
      if (!ok) return
    }
    setBusy(true)
    try {
      const b = await unwrap(
        api.POST('/api/v1/evaluations', {
          params: { header: { 'Idempotency-Key': newIdempotencyKey() } },
          body: {
            case_ids: picked,
            modes,
            repetitions: reps,
            evidence_policy: evidence,
            blind_rating: true,
            max_trials: MAX,
          },
        }),
      )
      onCreated(b.id)
    } catch (e) {
      notify(e instanceof ApiError ? e.error.message : 'The batch was not created.', 'error')
    } finally {
      setBusy(false)
    }
  }
  return (
    <section
      aria-labelledby="new-batch"
      className="rounded-card border border-border bg-surface p-5"
    >
      <h2 id="new-batch" className="text-[19px] font-semibold">
        New matched batch
      </h2>
      <p className="mt-1 text-[14px] text-muted">
        Each selected case runs once per condition and repetition with the same idea, constraints,
        scripted follow-ups and settings.{' '}
        {settings.data?.provider_mode === 'demo'
          ? 'Demo mode: results test the mechanics only.'
          : ''}
      </p>
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <label className="text-[14px]" htmlFor="lab-domain">
          Domain
        </label>
        <select
          id="lab-domain"
          value={domain}
          onChange={(e) => setDomain(e.target.value)}
          className="min-h-10 rounded-control border border-border bg-surface px-2"
        >
          <option value="all">All domains</option>
          {domains.map((d) => (
            <option key={d} value={d}>
              {d}
            </option>
          ))}
        </select>
        <button
          type="button"
          className={secondaryButton}
          onClick={() => setPicked((p) => [...new Set([...p, ...shown.map((c) => c.id)])])}
        >
          Select shown
        </button>
        <button type="button" className={secondaryButton} onClick={() => setPicked([])}>
          Clear
        </button>
      </div>
      <fieldset className="mt-3 max-h-64 overflow-y-auto rounded-control border border-border p-2">
        <legend className="px-1 text-[14px] font-medium">
          Cases ({picked.length} selected of {cases.data?.items.length ?? 0})
        </legend>
        {shown.map((c) => (
          <label
            key={c.id}
            className="flex min-h-10 items-start gap-2 rounded-control px-2 py-1 hover:bg-surface-subtle"
          >
            <input
              type="checkbox"
              checked={picked.includes(c.id)}
              onChange={(e) =>
                setPicked((p) => (e.target.checked ? [...p, c.id] : p.filter((x) => x !== c.id)))
              }
              className="mt-1 size-4 accent-[var(--accent)]"
            />
            <span className="text-[14px]">
              <span className="font-medium">{c.id}</span> · {c.domain} — {c.idea}
            </span>
          </label>
        ))}
      </fieldset>
      <fieldset className="mt-4">
        <legend className="font-medium">Conditions</legend>
        {MODES.map((m) => (
          <label key={m.value} className="mt-1 flex min-h-9 items-center gap-2 text-[14px]">
            <input
              type="checkbox"
              checked={modes.includes(m.value)}
              onChange={(e) =>
                setModes((x) =>
                  e.target.checked ? [...x, m.value] : x.filter((v) => v !== m.value),
                )
              }
              className="size-4 accent-[var(--accent)]"
            />
            <span className="font-medium">{m.label}</span>{' '}
            <span className="text-muted">— {m.hint}</span>
          </label>
        ))}
      </fieldset>
      <div className="mt-4 flex flex-wrap gap-6">
        <label className="text-[14px]">
          <span className="block font-medium">Repetitions</span>
          <select
            value={reps}
            onChange={(e) => setReps(Number(e.target.value))}
            className="mt-1 min-h-10 rounded-control border border-border bg-surface px-2"
          >
            {[1, 2, 3, 4, 5].map((n) => (
              <option key={n}>{n}</option>
            ))}
          </select>
        </label>
        <fieldset>
          <legend className="text-[14px] font-medium">Evidence</legend>
          {EVIDENCE.map((e) => (
            <label key={e.value} className="mt-1 flex min-h-9 items-center gap-2 text-[14px]">
              <input
                type="radio"
                name="evidence"
                checked={evidence === e.value}
                onChange={() => setEvidence(e.value)}
                className="size-4 accent-[var(--accent)]"
              />
              <span className="font-medium">{e.label}</span>{' '}
              <span className="text-muted">— {e.hint}</span>
            </label>
          ))}
        </fieldset>
      </div>
      <p className={'mt-4 font-medium ' + (planned > MAX ? 'text-danger' : '')} aria-live="polite">
        {planned} trials planned (limit {MAX})
        {planned > MAX ? ' — choose fewer cases, conditions or repetitions' : ''}
      </p>
      <button
        type="button"
        disabled={busy || planned === 0 || planned > MAX || modes.length === 0}
        onClick={() => void run()}
        className={primaryButton + ' mt-2'}
      >
        {busy ? 'Creating…' : 'Run batch'}
      </button>
    </section>
  )
}

function BatchView({ id }: { id: string }) {
  const qc = useQueryClient()
  const batch = useQuery({
    queryKey: ['lab-batch', id],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/evaluations/{evaluation_id}', { params: { path: { evaluation_id: id } } }),
      ),
    refetchInterval: (q) =>
      q.state.data && ['queued', 'running'].includes(q.state.data.status) ? 2000 : false,
  })
  const b = batch.data
  if (batch.isError) return <p role="alert">This batch could not load: {batch.error.message}</p>
  if (!b) return <p className="text-muted">Loading batch…</p>
  const done = b.finished_trials + b.failed_trials
  const active = b.status === 'queued' || b.status === 'running'
  const exportAs = async (format: 'csv' | 'json') => {
    const ok = await dialogs.confirm({
      title: 'Export reveals the conditions',
      body: 'The export lists which output came from which condition and marks every trial as revealed.',
      confirmLabel: `Export ${format.toUpperCase()}`,
    })
    if (!ok) return
    const r = await fetch(`/api/v1/evaluations/${id}/export?format=${format}`)
    if (!r.ok) return notify('Export failed.', 'error')
    const url = URL.createObjectURL(await r.blob())
    const a = document.createElement('a')
    a.href = url
    a.download =
      /filename="([^"]+)"/.exec(r.headers.get('content-disposition') ?? '')?.[1] ??
      `evaluation.${format}`
    a.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
  return (
    <section
      aria-labelledby="batch-heading"
      className="rounded-card border border-border bg-surface p-5"
    >
      <div className="flex flex-wrap items-center gap-3">
        <h2 id="batch-heading" className="flex-1 text-[19px] font-semibold">
          Batch {id.slice(0, 8)} · {b.status}
        </h2>
        {active && (
          <button
            type="button"
            className={secondaryButton}
            onClick={async () => {
              await unwrap(
                api.POST('/api/v1/evaluations/{evaluation_id}/cancel', {
                  params: { path: { evaluation_id: id } },
                }),
              )
              await qc.invalidateQueries({ queryKey: ['lab-batch', id] })
            }}
          >
            Cancel batch
          </button>
        )}
        <button type="button" className={secondaryButton} onClick={() => void exportAs('csv')}>
          Export CSV
        </button>
        <button type="button" className={secondaryButton} onClick={() => void exportAs('json')}>
          Export JSON
        </button>
      </div>
      <p className="mt-1 text-[14px] text-muted">
        {b.config.case_ids.length} cases × {b.config.modes.length} conditions ×{' '}
        {b.config.repetitions} · evidence {b.config.evidence_policy}
      </p>
      <div
        className="mt-3"
        role="progressbar"
        aria-label="Trials finished"
        aria-valuemin={0}
        aria-valuemax={b.planned_trials}
        aria-valuenow={done}
      >
        <div className="h-2 rounded-full bg-surface-subtle">
          <div
            className="h-2 rounded-full bg-accent"
            style={{ width: `${b.planned_trials ? (done / b.planned_trials) * 100 : 0}%` }}
          />
        </div>
        <p className="mt-1 text-[14px]">
          {b.finished_trials} completed · {b.failed_trials} incomplete · {b.planned_trials - done}{' '}
          not finished of {b.planned_trials}
        </p>
      </div>
      <Tabs.Root defaultValue="rate" className="mt-4">
        <Tabs.List aria-label="Batch" className="flex gap-1 border-b border-border">
          {[
            ['rate', 'Rate (blind)'],
            ['results', 'Results'],
          ].map(([v, l]) => (
            <Tabs.Trigger
              key={v}
              value={v}
              className="min-h-11 border-b-2 border-transparent px-3 text-muted data-[state=active]:border-selection-border data-[state=active]:text-text"
            >
              {l}
            </Tabs.Trigger>
          ))}
        </Tabs.List>
        <Tabs.Content value="rate" className="pt-4">
          <RatingView batch={b} />
        </Tabs.Content>
        <Tabs.Content value="results" className="pt-4">
          <ResultsView batch={b} />
        </Tabs.Content>
      </Tabs.Root>
    </section>
  )
}

export function LabPage() {
  const qc = useQueryClient()
  const [params, setParams] = useSearchParams()
  const selected = params.get('batch')
  const batches = useQuery({
    queryKey: ['lab-batches'],
    queryFn: () => unwrap(api.GET('/api/v1/evaluations', { params: { query: { limit: 30 } } })),
    refetchInterval: (q) =>
      q.state.data?.items.some((b) => ['queued', 'running'].includes(b.status)) ? 3000 : false,
  })
  return (
    <section className="mx-auto max-w-[var(--layout-workspace-max)] px-4 py-8 sm:px-6 lg:px-12">
      <h1 className="text-[length:var(--text-title)] leading-tight font-semibold">
        Experiment Lab
      </h1>
      <p className="mt-2 max-w-[68ch] text-muted">
        Compare Standard, Fixed panel and Jev-guided on matched cases, rate the outputs blind, then
        reveal and read the measured differences. The seed cases are a pilot set, not a validated
        benchmark; a better score is not assumed.
      </p>
      <div className="mt-6 grid gap-6">
        <NewBatch
          onCreated={(id) => {
            setParams({ batch: id })
            void qc.invalidateQueries({ queryKey: ['lab-batches'] })
          }}
        />
        <section aria-labelledby="batches">
          <h2 id="batches" className="text-[19px] font-semibold">
            Batches
          </h2>
          {batches.data?.items.length === 0 && <p className="mt-1 text-muted">No batches yet.</p>}
          <ul className="mt-2 flex flex-wrap gap-2">
            {batches.data?.items.map((b) => (
              <li key={b.id}>
                <button
                  type="button"
                  aria-current={selected === b.id ? 'true' : undefined}
                  onClick={() => setParams({ batch: b.id })}
                  className="min-h-10 rounded-control border border-border px-3 text-[14px] aria-[current=true]:border-selection-border aria-[current=true]:bg-selection-surface"
                >
                  {b.id.slice(0, 8)} · {b.status} · {b.finished_trials}/{b.planned_trials}
                </button>
              </li>
            ))}
          </ul>
        </section>
        {selected && <BatchView key={selected} id={selected} />}
      </div>
    </section>
  )
}
