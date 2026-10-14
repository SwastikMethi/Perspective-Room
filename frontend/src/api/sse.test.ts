import type { Schemas } from './client'
import { upsertMessages } from './queries'
import { subscribeRunEvents } from './sse'

type Listener = (e: MessageEvent) => void

class FakeEventSource {
  static instances: FakeEventSource[] = []
  static CLOSED = 2
  url: string
  readyState = 1
  onerror: ((e: Event) => void) | null = null
  listeners = new Map<string, Listener[]>()
  closed = false

  constructor(url: string) {
    this.url = url
    FakeEventSource.instances.push(this)
  }
  addEventListener(type: string, fn: Listener) {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), fn])
  }
  close() {
    this.closed = true
    this.readyState = 2
  }
  emit(type: string, id: string, data: unknown) {
    const envelope = { id, run_id: 'r1', type, created_at: '2026-10-15T00:00:00Z', data }
    for (const fn of this.listeners.get(type) ?? [])
      fn(new MessageEvent(type, { data: JSON.stringify(envelope), lastEventId: id }))
  }
  fail() {
    this.readyState = 2
    this.onerror?.(new Event('error'))
  }
}

const message = (id: string, sequence: number) =>
  ({
    id,
    session_id: 's1',
    run_id: 'r1',
    sequence,
    role: 'persona',
    persona_id: 'mentor',
    text: null,
    contribution: null,
    summary: null,
    created_at: '2026-10-15T00:00:00Z',
    warning_codes: [],
  }) as Schemas['Message']

beforeEach(() => {
  FakeEventSource.instances = []
})

describe('subscribeRunEvents', () => {
  it('delivers each event once even when replayed twice, and closes on terminal', () => {
    const seen: string[] = []
    const onTerminal = vi.fn()
    subscribeRunEvents({
      runId: 'r1',
      after: null,
      onEvent: (e) => seen.push(e.id),
      onTerminal,
      onLost: vi.fn(),
      EventSourceImpl: FakeEventSource as unknown as typeof EventSource,
    })
    const es = FakeEventSource.instances[0]
    expect(es.url).toBe('/api/v1/runs/r1/events')
    es.emit('message.completed', '5', { message: message('m1', 2), session_version: 3 })
    es.emit('message.completed', '5', { message: message('m1', 2), session_version: 3 })
    es.emit('run.completed', '6', { run: {}, missing_persona_ids: [] })
    expect(seen).toEqual(['5', '6'])
    expect(es.closed).toBe(true)
    expect(onTerminal).toHaveBeenCalledOnce()
  })

  it('resumes after the last seen id and reports a lost stream once the source is closed', () => {
    const onLost = vi.fn()
    const sub = subscribeRunEvents({
      runId: 'r1',
      after: '41',
      onEvent: () => {},
      onTerminal: () => {},
      onLost,
      EventSourceImpl: FakeEventSource as unknown as typeof EventSource,
    })
    const es = FakeEventSource.instances[0]
    expect(es.url).toBe('/api/v1/runs/r1/events?after=41')
    es.emit('run.stage', '42', { stage: 'drafting', persona_id: 'mentor', status_key: 'x' })
    es.fail()
    expect(onLost).toHaveBeenCalledWith('42')
    expect(sub.lastEventId()).toBe('42')
    sub.close()
  })
})

describe('upsertMessages', () => {
  it('dedupes by id and keeps sequence order', () => {
    const list = {
      items: [message('a', 1), message('c', 3)],
      next_cursor: null,
      previous_cursor: null,
    }
    const out = upsertMessages(list, [message('b', 2), message('c', 3)])
    expect(out.items.map((m) => m.id)).toEqual(['a', 'b', 'c'])
    expect(upsertMessages(undefined, [message('x', 9)]).items).toHaveLength(1)
  })
})
