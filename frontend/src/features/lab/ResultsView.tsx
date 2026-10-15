import { useState } from 'react'
import { api, ApiError, type Schemas, unwrap } from '../../api/client'
import { dialogs } from '../../components/Dialogs'

const MODE = {
  standard: 'Standard (A)',
  fixed_panel: 'Fixed panel (B)',
  jev_guided: 'Jev-guided (C)',
}
const METRIC = {
  useful_breadth: 'Useful breadth',
  usefulness: 'Usefulness',
  consistency: 'Personality consistency',
  redundancy: 'Redundancy (lower is better)',
}

export function median(values: number[]): number | null {
  if (!values.length) return null
  const s = [...values].sort((a, b) => a - b)
  const mid = Math.floor(s.length / 2)
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2
}

const num = (v: number | null | undefined, digits = 2) => (v == null ? '—' : v.toFixed(digits))
const signed = (v: number | null) => (v == null ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(2)}`)

export function ResultsTables({ results }: { results: Schemas['EvaluationResults'] }) {
  const cell = 'border-b border-border px-3 py-2 text-left'
  return (
    <div className="space-y-6">
      <section>
        <h3 className="font-semibold">Before comparing</h3>
        <ul aria-label="Before comparing" className="mt-1 list-disc pl-5 text-[15px]">
          {results.warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      </section>
      <div className="overflow-x-auto">
        <table aria-label="Conditions" className="w-full min-w-[640px] border-collapse text-[14px]">
          <thead>
            <tr className="text-muted">
              {[
                'Condition',
                'Planned',
                'Completed',
                'Incomplete',
                'Degraded',
                'Rated',
                'Breadth',
                'Usefulness',
                'Consistency',
                'Redundancy',
                'Median time',
                'Cost',
              ].map((h) => (
                <th key={h} scope="col" className={cell + ' font-medium'}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {results.conditions.map((c) => (
              <tr key={c.mode}>
                <th scope="row" className={cell + ' font-medium'}>
                  {MODE[c.mode]}
                </th>
                <td className={cell}>{c.planned}</td>
                <td className={cell}>{c.completed}</td>
                <td className={cell}>{c.incomplete}</td>
                <td className={cell}>{c.degraded}</td>
                <td className={cell}>{c.rated_trials}</td>
                <td className={cell}>{num(c.mean_useful_breadth)}</td>
                <td className={cell}>{num(c.mean_usefulness)}</td>
                <td className={cell}>{c.mode === 'standard' ? 'n/a' : num(c.mean_consistency)}</td>
                <td className={cell}>{num(c.mean_redundancy)}</td>
                <td className={cell}>
                  {c.median_elapsed_ms == null
                    ? '—'
                    : `${(c.median_elapsed_ms / 1000).toFixed(1)} s`}
                </td>
                <td className={cell}>
                  {c.estimated_cost_usd == null ? 'unknown' : `$${c.estimated_cost_usd.toFixed(4)}`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <section>
        <h3 className="font-semibold">Paired differences by case</h3>
        {results.comparisons.length === 0 && (
          <p className="text-muted">
            No comparison is possible: the batch needs Jev-guided plus at least one other condition.
          </p>
        )}
        <ul className="mt-2 space-y-3">
          {results.comparisons.map((c) => {
            const diffs = c.case_differences.map((d) => d.difference)
            const exploratory = c.ci95_low == null && c.matched_cases > 0
            return (
              <li
                key={`${c.left}-${c.right}-${c.metric}-${c.interpretation}`}
                className="rounded-card border border-border p-3"
              >
                <p className="font-medium">
                  {MODE[c.left]} − {MODE[c.right]} · {METRIC[c.metric]}
                </p>
                <p className="text-[13px] text-muted">{c.interpretation}</p>
                {c.matched_cases === 0 ? (
                  <p className="mt-1 text-[14px]">No matched rated cases yet.</p>
                ) : (
                  <>
                    <p className="mt-1 text-[14px]">
                      {c.matched_cases} matched cases · mean {signed(c.mean_difference)} · median{' '}
                      {signed(median(diffs))}
                      {exploratory
                        ? ' · Exploratory — fewer than 5 matched cases, no interval'
                        : ` · 95% interval ${signed(c.ci95_low)} to ${signed(c.ci95_high)}`}
                    </p>
                    <p className="mt-1 flex flex-wrap gap-x-3 text-[13px] text-muted">
                      {c.case_differences.map((d) => (
                        <span key={d.case_id}>
                          {d.case_id}: {signed(d.difference)}
                        </span>
                      ))}
                    </p>
                  </>
                )}
              </li>
            )
          })}
        </ul>
      </section>
    </div>
  )
}

/** Results reveal the conditions: they load only on an explicit, confirmed action (G20). */
export function ResultsView({ batch }: { batch: Schemas['Evaluation'] }) {
  const [results, setResults] = useState<Schemas['EvaluationResults'] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const show = async () => {
    const ok = await dialogs.confirm({
      title: 'Reveal conditions and show results?',
      body: 'This marks every trial in the batch as revealed. Ratings saved afterwards are recorded as unblinded.',
      confirmLabel: 'Reveal and show results',
    })
    if (!ok) return
    try {
      setResults(
        await unwrap(
          api.GET('/api/v1/evaluations/{evaluation_id}/results', {
            params: { path: { evaluation_id: batch.id }, query: { reveal: true } },
          }),
        ),
      )
      setError(null)
    } catch (e) {
      setError(e instanceof ApiError ? e.error.message : 'Results could not load.')
    }
  }
  return (
    <div>
      {!results && (
        <div>
          <p className="text-muted">
            Results are hidden while you rate, so knowing the condition cannot sway a rating.
          </p>
          <button
            type="button"
            onClick={() => void show()}
            className="mt-3 min-h-10 rounded-control bg-accent px-4 font-medium text-on-accent"
          >
            Reveal and show results
          </button>
        </div>
      )}
      {error && (
        <p role="alert" className="mt-2">
          {error}
        </p>
      )}
      {results && <ResultsTables results={results} />}
    </div>
  )
}
