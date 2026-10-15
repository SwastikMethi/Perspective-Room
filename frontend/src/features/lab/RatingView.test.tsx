import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import type { Schemas } from '../../api/client'
import { RatingView } from './RatingView'

const batch = {
  id: 'b1',
  status: 'completed',
  planned_trials: 1,
  finished_trials: 1,
  failed_trials: 0,
  config: {
    case_ids: ['case_01'],
    modes: ['standard'],
    repetitions: 1,
    evidence_policy: 'off',
    blind_rating: true,
    max_trials: 90,
  },
  created_at: '',
  updated_at: '',
} as Schemas['Evaluation']

afterEach(() => vi.unstubAllGlobals())

test('the blind rating view still works when the browser blocks storage', async () => {
  const blocked = Object.getOwnPropertyDescriptor(window, 'localStorage')
  Object.defineProperty(window, 'localStorage', {
    configurable: true,
    get() {
      throw new DOMException('The operation is insecure.', 'SecurityError')
    },
  })
  vi.stubGlobal(
    'fetch',
    async () =>
      new Response(JSON.stringify({ items: [], next_cursor: null }), {
        headers: { 'Content-Type': 'application/json' },
      }),
  )
  try {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <RatingView batch={batch} />
      </QueryClientProvider>,
    )
    expect(screen.getByLabelText('Rater alias')).toBeInTheDocument()
  } finally {
    if (blocked) Object.defineProperty(window, 'localStorage', blocked)
  }
})
