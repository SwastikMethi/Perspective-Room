import { render, screen, within } from '@testing-library/react'
import type { Schemas } from '../../api/client'
import { median, ResultsTables } from './ResultsView'

const cond = (
  mode: Schemas['ConditionResult']['mode'],
  over: Partial<Schemas['ConditionResult']> = {},
) => ({
  mode,
  planned: 4,
  completed: 3,
  incomplete: 1,
  degraded: 0,
  rated_trials: 0,
  mean_useful_breadth: null,
  mean_usefulness: null,
  mean_consistency: null,
  mean_redundancy: null,
  median_elapsed_ms: null,
  estimated_cost_usd: null,
  ...over,
})

const results = (comparisons: Schemas['PairedComparison'][]): Schemas['EvaluationResults'] => ({
  evaluation_id: 'e1',
  provider_mode: 'demo',
  evidence_policy: 'off',
  conditions: [cond('standard'), cond('fixed_panel'), cond('jev_guided', { degraded: 1 })],
  comparisons,
  ratings: [],
  warnings: [
    'Planned 12 trials; 9 completed, 3 incomplete.',
    'Demo provider: never a live-model effectiveness result.',
  ],
})

test('median is computed client-side from case differences', () => {
  expect(median([3, 1, 2])).toBe(2)
  expect(median([1, 2, 3, 4])).toBe(2.5)
  expect(median([])).toBeNull()
})

test('denominators come first; missing means stay empty, never zero', () => {
  render(<ResultsTables results={results([])} />)
  const notes = screen.getByRole('list', { name: 'Before comparing' })
  expect(within(notes).getAllByRole('listitem')[0]).toHaveTextContent('Planned 12 trials')
  const table = screen.getByRole('table', { name: 'Conditions' })
  expect(within(table).getAllByText('—').length).toBeGreaterThan(0)
  expect(within(table).queryByText('0.00')).toBeNull()
  expect(screen.getByText(/Demo provider/)).toBeInTheDocument()
})

test('small samples are labeled exploratory with raw points and no interval', () => {
  render(
    <ResultsTables
      results={results([
        {
          left: 'jev_guided',
          right: 'fixed_panel',
          metric: 'useful_breadth',
          matched_cases: 3,
          mean_difference: 0.5,
          ci95_low: null,
          ci95_high: null,
          case_differences: [
            { case_id: 'case_01', difference: 1 },
            { case_id: 'case_02', difference: 0 },
            { case_id: 'case_03', difference: 0.5 },
          ],
          interpretation: 'intent-to-treat: exploratory — fewer than 5 matched cases, no interval',
        },
      ])}
    />,
  )
  expect(screen.getByText(/Exploratory — fewer than 5 matched cases/)).toBeInTheDocument()
  expect(screen.getByText('case_01: +1.00')).toBeInTheDocument()
  expect(screen.getByText(/median \+0\.50/)).toBeInTheDocument()
})
