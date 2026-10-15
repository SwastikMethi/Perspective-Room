import { useDrafts } from '../../stores/drafts'
import { sendNewChat } from './send'

const session = {
  id: 's1',
  version: 1,
} as const

function jsonResponse(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('sendNewChat', () => {
  beforeEach(() => {
    localStorage.clear()
    useDrafts.setState({ drafts: {} })
  })

  it('resends the exact create and turn requests after a lost response', async () => {
    const calls: { url: string; key: string | null; body: string }[] = []
    let turnAttempts = 0
    vi.stubGlobal('fetch', async (input: Request) => {
      const req = input instanceof Request ? input : new Request(input)
      calls.push({
        url: new URL(req.url).pathname,
        key: req.headers.get('Idempotency-Key'),
        body: await req.text(),
      })
      if (req.url.endsWith('/sessions')) return jsonResponse(201, session)
      turnAttempts += 1
      if (turnAttempts === 1) throw new TypeError('network down') // response lost
      return jsonResponse(202, { id: 'r1' })
    })

    await expect(sendNewChat('new:unfiled', { idea: 'Tool sharing' })).rejects.toThrow()
    expect(useDrafts.getState().get('new:unfiled')?.pending?.sessionId).toBe('s1')

    await expect(sendNewChat('new:unfiled', { idea: 'Tool sharing' })).resolves.toBe('s1')
    const creates = calls.filter((c) => c.url === '/api/v1/sessions')
    const turns = calls.filter((c) => c.url.endsWith('/turns'))
    expect(new Set(creates.map((c) => c.key)).size).toBe(1)
    expect(new Set(turns.map((c) => c.key)).size).toBe(1)
    expect(turns[0].body).toBe(turns[1].body)
    expect(creates[0].key).not.toBe(turns[0].key)
    expect(useDrafts.getState().get('new:unfiled')).toBeUndefined()
    vi.unstubAllGlobals()
  })

  it('drops the keys after a definitive error so an edited retry is a new request', async () => {
    vi.stubGlobal('fetch', async () =>
      jsonResponse(503, {
        code: 'provider_not_ready',
        message: 'OpenAI is not configured.',
        retryable: false,
        request_id: 'r',
        details: {},
      }),
    )
    await expect(sendNewChat('new:unfiled', { idea: 'x' })).rejects.toThrow(
      'OpenAI is not configured.',
    )
    expect(useDrafts.getState().get('new:unfiled')?.pending).toBeUndefined()
    vi.unstubAllGlobals()
  })
})

describe('sendTurn', () => {
  beforeEach(() => {
    localStorage.clear()
    useDrafts.setState({ drafts: {} })
  })

  it('keeps text typed while an uncertain send was retried', async () => {
    const { sendTurn } = await import('./send')
    vi.stubGlobal('fetch', async () => jsonResponse(202, { id: 'r1' }))
    useDrafts.getState().set('s1', { text: 'edited after the lost response' })
    useDrafts.getState().set('s1', {
      pending: {
        turnKey: 'k',
        turnBody: { expected_version: 1, message: 'original', control: {} as never },
      },
    })
    // Resending the earlier request (same body) settles it without touching the newer text.
    await sendTurn('s1', { expected_version: 1, message: 'original', control: {} as never })
    expect(useDrafts.getState().get('s1')?.text).toBe('edited after the lost response')
    expect(useDrafts.getState().get('s1')?.pending).toBeUndefined()
    vi.unstubAllGlobals()
  })

  it('never sends an uncertain earlier request in place of different new text', async () => {
    const { sendTurn, PendingConflict } = await import('./send')
    const fetchSpy = vi.fn(async () => jsonResponse(202, { id: 'r1' }))
    vi.stubGlobal('fetch', fetchSpy)
    useDrafts.getState().set('s1', {
      pending: {
        turnKey: 'k',
        turnBody: { expected_version: 1, message: 'FIRST', control: {} as never },
      },
    })
    const err = await sendTurn('s1', {
      expected_version: 1,
      message: 'SECOND',
      control: {} as never,
    }).catch((e) => e)
    expect(err).toBeInstanceOf(PendingConflict)
    expect(err.earlier).toBe('FIRST')
    expect(fetchSpy).not.toHaveBeenCalled()
    vi.unstubAllGlobals()
  })

  it('a summary uses its own key, so it never replays a pending message', async () => {
    const { sendTurn } = await import('./send')
    const sent: { key: string | null; body: string }[] = []
    vi.stubGlobal('fetch', async (req: Request) => {
      sent.push({ key: req.headers.get('Idempotency-Key'), body: await req.text() })
      return jsonResponse(202, { id: 'r2' })
    })
    useDrafts.getState().set('s1', {
      pending: {
        turnKey: 'k',
        turnBody: { expected_version: 1, message: 'FIRST', control: {} as never },
      },
    })
    await sendTurn(
      's1',
      { expected_version: 1, message: 'Summarize', control: {} as never },
      'summary:s1',
    )
    expect(sent).toHaveLength(1)
    expect(sent[0].key).not.toBe('k')
    expect(JSON.parse(sent[0].body).message).toBe('Summarize')
    expect(useDrafts.getState().get('s1')?.pending?.turnKey).toBe('k')
    vi.unstubAllGlobals()
  })

  it('a first send whose idea changed after a lost response asks instead of resending', async () => {
    const { sendNewChat, PendingConflict } = await import('./send')
    const fetchSpy = vi.fn(async () => jsonResponse(201, { id: 's1', version: 1 }))
    vi.stubGlobal('fetch', fetchSpy)
    useDrafts.getState().set('new:unfiled', {
      pending: { createKey: 'c', createBody: { idea: 'Old idea' }, turnKey: 't' },
    })
    await expect(sendNewChat('new:unfiled', { idea: 'New idea' })).rejects.toBeInstanceOf(
      PendingConflict,
    )
    expect(fetchSpy).not.toHaveBeenCalled()
    vi.unstubAllGlobals()
  })
})
