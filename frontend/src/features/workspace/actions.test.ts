import { QueryClient } from '@tanstack/react-query'
import { useDrafts } from '../../stores/drafts'
import { duplicateChat } from './actions'

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

beforeEach(() => {
  localStorage.clear()
  useDrafts.setState({ drafts: {} })
})
afterEach(() => vi.unstubAllGlobals())

test('a duplicate whose response was lost is retried with the same key (no second copy, T35)', async () => {
  const forkKeys: (string | null)[] = []
  let attempts = 0
  vi.stubGlobal('fetch', async (req: Request) => {
    if (req.method === 'GET') return json(200, { id: 'a', version: 3 })
    forkKeys.push(req.headers.get('Idempotency-Key'))
    attempts += 1
    if (attempts === 1) throw new TypeError('connection reset') // server did it; response lost
    return json(201, { session: { id: 'copy-1' }, turn_template: null })
  })
  const qc = new QueryClient()
  const chat = {
    id: 'a',
    title: 'Garden',
    folder_id: null,
    is_pinned: false,
    is_archived: false,
    organization_version: 1,
    active_run_id: null,
  }
  expect(await duplicateChat(qc, chat)).toBeNull()
  expect(await duplicateChat(qc, chat)).toBe('copy-1')
  expect(forkKeys).toHaveLength(2)
  expect(forkKeys[0]).toBe(forkKeys[1])
  expect(useDrafts.getState().get('dup:a')).toBeUndefined() // cleared after success
})
