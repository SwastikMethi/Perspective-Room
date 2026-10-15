// Plain-text copy (doc 03: attribution and citation URLs kept) and the G2 warning sentences
// (mirrors backend app/domain/internal.py WARNING_TEXT).
import type { Schemas } from '../../api/client'

export const WARNING_TEXT: Record<string, string> = {
  coordination_fallback: 'Fixed order used for this turn.',
  coordination_unavailable: 'Jev was unavailable; fixed order used for this turn.',
  coordination_low_confidence: 'Jev was not confident; fixed order used for this turn.',
  audit_unavailable: 'Quality checks were unavailable for some replies.',
  quality_warning: 'A reply was published with a quality warning.',
  repair_used: 'One reply was revised once after a quality check.',
  research_unavailable: 'Current facts were not checked; replies use labeled assumptions.',
  research_empty: 'The search found no usable sources; nothing was verified.',
  research_findings_dropped: 'Research findings without valid sources were dropped.',
  memory_unavailable: 'The conversation memory was not updated after this turn.',
  contribution_failed: 'Some replies could not be produced.',
  deadline_exceeded: 'The turn reached its time limit.',
  usage_unknown: 'Some provider usage is unknown.',
  demo_mode: 'Demo mode — deterministic fixtures, no external calls.',
  budget_cap_unenforced: 'The session cost cap cannot be enforced (no rate card).',
  intake_unavailable: 'The turn was read without the usual intake step.',
  attempts_exhausted: 'The turn reached its limit of provider calls.',
}

export const warningText = (code: string) => WARNING_TEXT[code] ?? code

export const SECTION_LABELS: Record<string, string> = {
  directions: 'Directions',
  disagreements: 'Disagreements',
  assumptions: 'Assumptions',
  questions: 'Open questions',
  experiments: 'Experiments',
}

export function copyText(
  m: Schemas['Message'],
  speaker: string,
  sources: Map<string, { title: string; url: string }>,
): string {
  const numbers = new Map<string, number>()
  const cite = (ids: string[]) => {
    const marks = ids
      .filter((id) => sources.has(id))
      .map((id) => {
        if (!numbers.has(id)) numbers.set(id, numbers.size + 1)
        return `[${numbers.get(id)}]`
      })
    return marks.length ? ` ${marks.join('')}` : ''
  }
  const lines: string[] = []
  if (m.contribution) {
    const c = m.contribution
    lines.push(`${speaker} — ${c.headline}`, '')
    for (const b of c.blocks) lines.push(`${b.text}${cite(b.source_ids)}`)
    lines.push('', `New angle: ${c.new_angle}`)
    if (c.next_question) lines.push(`Next question: ${c.next_question}`)
  } else if (m.summary) {
    lines.push(`${speaker} — Summary`)
    for (const s of m.summary.sections) {
      lines.push('', SECTION_LABELS[s.kind] ?? s.kind)
      for (const i of s.items) lines.push(`- ${i.text}${cite(i.source_ids)}`)
    }
  } else {
    lines.push(speaker, '', m.text ?? '')
  }
  if (numbers.size) {
    lines.push('', 'Sources:')
    for (const [id, n] of numbers) {
      const s = sources.get(id)!
      lines.push(`[${n}] ${s.title} — ${s.url}`)
    }
  }
  return lines.join('\n')
}
