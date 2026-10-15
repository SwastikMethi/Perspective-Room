// Transcript structure: turn groups at user-message boundaries, columns by CONTENT width
// (doc 03), and per-group citation numbers in order of first appearance.
import type { Schemas } from '../../api/client'

type Message = Schemas['Message']

export interface TurnGroupData {
  key: string
  user: Message | null
  replies: Message[]
}

export function groupTurns(messages: Message[]): TurnGroupData[] {
  const groups: TurnGroupData[] = []
  for (const m of messages) {
    if (m.role === 'user') groups.push({ key: m.id, user: m, replies: [] })
    else if (groups.length === 0) groups.push({ key: `lead-${m.id}`, user: null, replies: [m] })
    else groups[groups.length - 1].replies.push(m)
  }
  return groups
}

export const columnsFor = (contentWidth: number) =>
  contentWidth >= 960 ? 3 : contentWidth >= 640 ? 2 : 1

export function citedIds(m: Message): string[] {
  if (m.contribution) return m.contribution.blocks.flatMap((b) => b.source_ids)
  if (m.summary) return m.summary.sections.flatMap((s) => s.items.flatMap((i) => i.source_ids))
  return []
}

export function numberSources(replies: Message[]): Map<string, number> {
  const numbers = new Map<string, number>()
  for (const m of replies)
    for (const id of citedIds(m)) if (!numbers.has(id)) numbers.set(id, numbers.size + 1)
  return numbers
}

/** Replies published by a later Retry of the round (a different run than the round's first
 * replies). They appear after their round-mates; the card says so instead of reordering. */
export function retriedIds(replies: Message[]): Set<string> {
  const first = replies.find((m) => m.run_id)?.run_id
  return new Set(replies.filter((m) => m.run_id && m.run_id !== first).map((m) => m.id))
}
