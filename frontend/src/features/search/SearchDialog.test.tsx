import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { highlight, SearchDialog } from './SearchDialog'

const page = (items: unknown[]) =>
  new Response(JSON.stringify({ items, next_cursor: null }), {
    headers: { 'Content-Type': 'application/json' },
  })

const hit = {
  id: 's1',
  title: 'Garden plans',
  mode: 'jev_guided',
  selected_persona_ids: ['mentor'],
  organization_version: 1,
  folder_id: null,
  is_pinned: false,
  is_archived: false,
  last_activity_at: '2026-10-15T00:00:00Z',
  active_run_id: null,
  created_at: '2026-10-15T00:00:00Z',
  updated_at: '2026-10-15T00:00:00Z',
  match: { kind: 'message', snippet: 'a budget for seeds', message_id: 'm1', message_sequence: 2 },
}

function setup() {
  const calls: { q: string | null; signal: AbortSignal }[] = []
  vi.stubGlobal('fetch', async (req: Request) => {
    const url = new URL(req.url)
    if (url.pathname === '/api/v1/folders') return page([])
    const q = url.searchParams.get('q')
    calls.push({ q, signal: req.signal })
    if (q === 'compost')
      return new Promise<Response>((_, reject) =>
        req.signal.addEventListener('abort', () =>
          reject(new DOMException('aborted', 'AbortError')),
        ),
      )
    return page(q === 'budget' ? [hit] : [])
  })
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter>
        <SearchDialog open onOpenChange={() => {}} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return calls
}

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

test('typing is debounced 250ms and only the settled query is requested', async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  const calls = setup()
  const box = screen.getByRole('textbox', { name: 'Search chats' })
  for (const q of ['b', 'bu', 'bud', 'budget']) {
    fireEvent.change(box, { target: { value: q } })
    await act(() => vi.advanceTimersByTimeAsync(100))
  }
  expect(calls).toHaveLength(0)
  await act(() => vi.advanceTimersByTimeAsync(300))
  expect(calls.map((c) => c.q)).toEqual(['budget'])
  expect(await screen.findByText('Garden plans')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: /Garden plans/ })).toHaveAttribute(
    'href',
    '/rooms/s1?message=m1',
  )
})

test('a newer query aborts the stale request', async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  const calls = setup()
  const box = screen.getByRole('textbox', { name: 'Search chats' })
  fireEvent.change(box, { target: { value: 'compost' } })
  await act(() => vi.advanceTimersByTimeAsync(300))
  fireEvent.change(box, { target: { value: 'budget' } })
  await act(() => vi.advanceTimersByTimeAsync(300))
  expect(calls.map((c) => c.q)).toEqual(['compost', 'budget'])
  expect(await screen.findByText('Garden plans')).toBeInTheDocument()
  expect(calls[0].signal.aborted).toBe(true)
})

test('no matches shows the query, Clear and Include archived', async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  setup()
  fireEvent.change(screen.getByRole('textbox', { name: 'Search chats' }), {
    target: { value: 'zzz' },
  })
  await act(() => vi.advanceTimersByTimeAsync(300))
  expect(await screen.findByText(/No chats match/)).toHaveTextContent('“zzz”')
  expect(screen.getByRole('button', { name: 'Clear search' })).toBeInTheDocument()
  expect(screen.getByLabelText('Include archived')).toBeInTheDocument()
})

test('highlight splits on every case-insensitive match without HTML', () => {
  expect(highlight('A <b>Budget</b> budget', 'budget')).toEqual([
    { text: 'A <b>', match: false },
    { text: 'Budget', match: true },
    { text: '</b> ', match: false },
    { text: 'budget', match: true },
  ])
})
