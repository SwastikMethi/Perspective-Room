import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { useIdeas } from './queries'

afterEach(() => vi.unstubAllGlobals())

test('all saved ideas load, not just the first page', async () => {
  const card = (i: number) => ({
    id: `c${i}`,
    session_id: 's',
    message_id: 'm',
    title: `Idea ${i}`,
    note: '',
    status: 'exploring',
    version: 1,
    created_at: '',
    updated_at: '',
  })
  vi.stubGlobal('fetch', async (req: Request) => {
    const cursor = new URL(req.url).searchParams.get('cursor')
    const body = cursor
      ? { items: [card(101)], next_cursor: null }
      : { items: Array.from({ length: 100 }, (_, i) => card(i)), next_cursor: 'next' }
    return new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } })
  })
  const qc = new QueryClient()
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
  const { result } = renderHook(() => useIdeas('s'), { wrapper })
  await waitFor(() => expect(result.current.data?.items).toHaveLength(101))
})
