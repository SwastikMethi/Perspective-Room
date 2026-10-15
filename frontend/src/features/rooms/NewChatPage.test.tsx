import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { useDrafts } from '../../stores/drafts'
import { NewChatPage } from './NewChatPage'

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

beforeEach(() => {
  localStorage.clear()
  useDrafts.setState({ drafts: {} })
})
afterEach(() => vi.unstubAllGlobals())

function setup() {
  const posts: string[] = []
  vi.stubGlobal('fetch', async (req: Request) => {
    const path = new URL(req.url).pathname
    if (req.method === 'POST') {
      posts.push(path)
      return path.endsWith('/turns') ? json({ id: 'r1' }, 202) : json({ id: 's1', version: 1 }, 201)
    }
    if (path === '/api/v1/personas') return json({ items: [], default_selection: ['mentor'] })
    if (path === '/api/v1/settings')
      return json({ provider_mode: 'demo', openai_configured: false, jev_configured: false })
    return json({ items: [], next_cursor: null })
  })
  useDrafts.getState().set('new:unfiled', {
    text: 'An idea that never got an answer',
    pending: {
      createKey: 'c1',
      createBody: { idea: 'An idea that never got an answer' },
      turnKey: 't1',
    },
  })
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <NewChatPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return posts
}

test('opening New chat never re-sends an interrupted first message by itself', async () => {
  const posts = setup()
  expect(await screen.findByText(/may not have been sent/)).toBeInTheDocument()
  await new Promise((r) => setTimeout(r, 50))
  expect(posts).toEqual([])
})

test('the user can resend it (same keys) or discard it', async () => {
  const posts = setup()
  fireEvent.click(await screen.findByRole('button', { name: 'Send it now' }))
  await waitFor(() => expect(posts).toEqual(['/api/v1/sessions', '/api/v1/sessions/s1/turns']))
})

test('discarding keeps the text but drops the pending request', async () => {
  setup()
  fireEvent.click(await screen.findByRole('button', { name: 'Discard the earlier send' }))
  expect(useDrafts.getState().get('new:unfiled')?.pending).toBeUndefined()
  expect(useDrafts.getState().get('new:unfiled')?.text).toBe('An idea that never got an answer')
})
