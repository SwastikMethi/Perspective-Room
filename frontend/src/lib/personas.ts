// Presentation data for the eight personas (handoff/config/persona-ui.json): roster order, short
// labels, accent dots and portrait crops in the approved mockups. Never alters persona prompts.
import ui from '@handoff/config/persona-ui.json'
import darkSprite from '../assets/approved-room-dark.png'
import lightSprite from '../assets/approved-room-light.png'
import type { Theme } from '../stores/ui'

export type PersonaId = (typeof ui.order)[number]

export interface PersonaUi {
  id: PersonaId
  label: string
  accent: string
  rect: { x: number; y: number; width: number; height: number }
}

export const ROSTER: PersonaId[] = [...ui.order]
export const PERSONA_UI: Record<string, PersonaUi> = Object.fromEntries(
  ui.personas.map((p) => [
    p.persona_id,
    { id: p.persona_id, label: p.short_label, accent: p.accent, rect: p.source_rect_px },
  ]),
)
const [SRC_W, SRC_H] = ui.source_size_px

export const shortLabel = (id: string | null | undefined) =>
  (id && PERSONA_UI[id]?.label) || 'Assistant'

/** Crop one portrait from the approved sprite: s = d/w; size W·s × H·s; offset −x·s, −y·s. */
export function spriteStyle(id: string, size: number, theme: Theme) {
  const p = PERSONA_UI[id]
  if (!p) return undefined
  const s = size / p.rect.width
  return {
    width: size,
    height: size,
    backgroundImage: `url(${theme === 'dark' ? darkSprite : lightSprite})`,
    backgroundSize: `${SRC_W * s}px ${SRC_H * s}px`,
    backgroundPosition: `${-p.rect.x * s}px ${-p.rect.y * s}px`,
    backgroundRepeat: 'no-repeat',
  } as const
}

/** Order any persona list by the fixed roster order. */
export const byRoster = <T extends string>(ids: readonly T[]) =>
  [...ids].sort((a, b) => ROSTER.indexOf(a as PersonaId) - ROSTER.indexOf(b as PersonaId))

// The sprites are large; warm both after startup so a theme switch never shows empty portraits.
// ponytail: whole-mockup sprites (1.5 MB each); crop per-portrait assets if load time matters.
if (typeof window !== 'undefined' && typeof Image !== 'undefined')
  setTimeout(() => {
    for (const src of [darkSprite, lightSprite]) new Image().src = src
  }, 1000)
