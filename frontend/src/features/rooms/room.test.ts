import type { Schemas } from '../../api/client'
import { columnsFor, groupTurns, numberSources } from './grouping'
import { copyText, warningText } from './copy'

type M = Schemas['Message']
const base = { session_id: 's', run_id: null, created_at: '', warning_codes: [] }
const user = (id: string, sequence: number, text = 'Q'): M =>
  ({
    ...base,
    id,
    sequence,
    role: 'user',
    persona_id: null,
    text,
    contribution: null,
    summary: null,
  }) as M
const reply = (id: string, sequence: number, persona: string, sources: string[] = []): M =>
  ({
    ...base,
    id,
    sequence,
    role: 'persona',
    persona_id: persona,
    text: null,
    summary: null,
    contribution: {
      headline: `H ${id}`,
      blocks: [
        { kind: 'suggestion', text: `Try ${id}.`, source_ids: [] },
        { kind: 'fact', text: `Fact ${id}.`, source_ids: sources },
      ],
      referenced_message_ids: [],
      new_angle: 'angle',
      next_question: 'What next?',
    },
  }) as M

test('turn groups split at user messages and keep publication order', () => {
  const groups = groupTurns([
    user('u1', 1),
    reply('a', 2, 'skeptic'),
    reply('b', 3, 'mentor'),
    user('u2', 4),
  ])
  expect(groups.map((g) => [g.user?.id ?? null, g.replies.map((r) => r.id)])).toEqual([
    ['u1', ['a', 'b']],
    ['u2', []],
  ])
  expect(groupTurns([reply('x', 1, 'mentor')])[0].user).toBeNull()
})

test('columns follow CONTENT width: 3 at ≥960, 2 at 640–959, 1 below 640', () => {
  expect(columnsFor(960)).toBe(3)
  expect(columnsFor(1280)).toBe(3)
  expect(columnsFor(700)).toBe(2)
  expect(columnsFor(640)).toBe(2)
  expect(columnsFor(500)).toBe(1)
  expect(columnsFor(0)).toBe(1)
})

test('sources are numbered once per group in order of first citation', () => {
  const nums = numberSources([
    reply('a', 2, 'mentor', ['s2', 's1']),
    reply('b', 3, 'skeptic', ['s1', 's3']),
  ])
  expect([...nums.entries()]).toEqual([
    ['s2', 1],
    ['s1', 2],
    ['s3', 3],
  ])
})

test('copy keeps attribution and citation URLs in plain text', () => {
  const sources = new Map([['s1', { title: 'Study', url: 'https://example.org/study' }]])
  const text = copyText(reply('a', 2, 'skeptic', ['s1']), 'Skeptical realist', sources)
  expect(text).toBe(
    [
      'Skeptical realist — H a',
      '',
      'Try a.',
      'Fact a. [1]',
      '',
      'New angle: angle',
      'Next question: What next?',
      '',
      'Sources:',
      '[1] Study — https://example.org/study',
    ].join('\n'),
  )
  expect(copyText(user('u', 1, 'My idea'), 'You', new Map())).toBe('You\n\nMy idea')
})

test('warning codes map to plain sentences; unknown codes stay visible', () => {
  expect(warningText('coordination_fallback')).toBe('Fixed order used for this turn.')
  expect(warningText('something_new')).toBe('something_new')
})

test('replies added by a later retry are identified (they publish after their round-mates)', async () => {
  const { retriedIds } = await import('./grouping')
  const a = { ...reply('a', 2, 'mentor'), run_id: 'run1' }
  const b = { ...reply('b', 3, 'explorer'), run_id: 'run1' }
  const c = { ...reply('c', 4, 'skeptic'), run_id: 'run2' }
  expect([...retriedIds([a, b, c])]).toEqual(['c'])
  expect([...retriedIds([a, b])]).toEqual([])
})
