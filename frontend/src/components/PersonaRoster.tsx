import { Check, ChevronLeft, ChevronRight, Info } from 'lucide-react'
import { Popover } from 'radix-ui'
import { useEffect, useRef, useState } from 'react'
import type { Schemas } from '../api/client'
import { PERSONA_UI, ROSTER } from '../lib/personas'
import { PersonaAvatar } from './PersonaAvatar'

function useOverflow() {
  const ref = useRef<HTMLDivElement>(null)
  const [edges, setEdges] = useState({ left: false, right: false })
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const update = () =>
      setEdges({
        left: el.scrollLeft > 2,
        right: el.scrollLeft + el.clientWidth < el.scrollWidth - 2,
      })
    update()
    el.addEventListener('scroll', update, { passive: true })
    const ro = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(update)
    ro?.observe(el)
    return () => {
      el.removeEventListener('scroll', update)
      ro?.disconnect()
    }
  }, [])
  return { ref, edges }
}

function Details({
  persona,
  onAsk,
}: {
  persona: Schemas['Persona'] | undefined
  onAsk?: () => void
}) {
  if (!persona) return null
  return (
    <Popover.Root>
      <Popover.Trigger
        aria-label={`About ${persona.display_name}`}
        className="absolute -top-1 -left-1 grid size-7 place-items-center rounded-full border border-border bg-surface text-muted opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 hover:text-text focus-visible:opacity-100 data-[state=open]:opacity-100 [@media(pointer:coarse)]:opacity-100"
      >
        <Info aria-hidden size={14} />
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          sideOffset={8}
          className="z-50 w-[min(320px,calc(100vw-24px))] rounded-card border border-border bg-surface p-4 text-text shadow-xl"
        >
          <p className="font-semibold">{persona.display_name}</p>
          <p className="mt-1 text-[14px] text-muted">{persona.tagline}</p>
          <p className="mt-3 text-[13px] font-medium">Cares about</p>
          <ul className="mt-1 list-disc pl-5 text-[14px]">
            {persona.priorities.map((p) => (
              <li key={p}>{p}</li>
            ))}
          </ul>
          {onAsk && (
            <Popover.Close
              onClick={onAsk}
              className="mt-4 inline-flex min-h-10 items-center rounded-control bg-accent px-3 font-medium text-on-accent hover:bg-accent-hover"
            >
              Ask {PERSONA_UI[persona.id]?.label ?? persona.display_name} directly
            </Popover.Close>
          )}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
}

/** All eight perspectives in one row (doc 03): labeled checkboxes with portrait, name and check.
 * Below 960px of roster width the row scrolls with visible edge affordances. */
export function PersonaRoster({
  selected,
  personas,
  defaultSelection,
  onChange,
  disabledReason,
  onAskDirectly,
  standard = false,
}: {
  selected: string[]
  personas: Schemas['Persona'][]
  defaultSelection: string[]
  onChange: (ids: string[]) => void
  disabledReason?: string | null
  onAskDirectly?: (id: string) => void
  standard?: boolean
}) {
  const { ref, edges } = useOverflow()
  const [notice, setNotice] = useState<string | null>(null)
  const byId = new Map(personas.map((p) => [p.id, p]))
  const all = selected.length === ROSTER.length
  const disabled = Boolean(disabledReason)

  const toggle = (id: string) => {
    if (disabled) return
    if (selected.includes(id)) {
      if (selected.length === 1) {
        setNotice('At least one perspective stays in the room. Select another first.')
        return
      }
      setNotice(null)
      onChange(ROSTER.filter((p) => p !== id && selected.includes(p)))
    } else {
      setNotice(null)
      onChange(ROSTER.filter((p) => p === id || selected.includes(p)))
    }
  }
  const scrollBy = (dx: number) => ref.current?.scrollBy({ left: dx, behavior: 'smooth' })

  return (
    <section aria-labelledby="roster-heading" className="mt-6">
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <h2 id="roster-heading" className="text-[18px] font-semibold">
          Choose perspectives
        </h2>
        <p className="text-[14px] text-muted" aria-live="polite">
          {selected.length} selected · {ROSTER.length} available
        </p>
        <button
          type="button"
          disabled={disabled}
          onClick={() => onChange(all ? [...defaultSelection] : [...ROSTER])}
          className="ml-auto min-h-10 rounded-control px-2 font-medium text-text underline decoration-selection-border decoration-2 underline-offset-4 hover:bg-surface-subtle disabled:opacity-60"
        >
          {all ? 'Use default trio' : 'Select all'}
        </button>
      </div>
      {standard && (
        <p className="mt-1 text-[14px] text-muted">
          Standard mode: one assistant answers each turn. The selection is kept for a later fork and
          is not sent to the assistant.
        </p>
      )}
      {disabledReason && <p className="mt-1 text-[14px] text-muted">{disabledReason}</p>}
      <div className="relative mt-3">
        <div
          ref={ref}
          role="group"
          aria-label="Perspectives in this room"
          className="flex snap-x gap-2 overflow-x-auto pt-2 pb-2 [scrollbar-width:thin]"
        >
          {ROSTER.map((id) => {
            const on = selected.includes(id)
            const ui = PERSONA_UI[id]
            return (
              <div
                key={id}
                className="group relative flex shrink-0 snap-start flex-col items-center"
              >
                <button
                  type="button"
                  role="checkbox"
                  aria-checked={on}
                  aria-disabled={disabled || undefined}
                  aria-label={`${ui.label}${byId.get(id) ? ` — ${byId.get(id)!.display_name}` : ''}`}
                  onClick={() => toggle(id)}
                  className="flex w-[104px] flex-col items-center gap-2 rounded-card px-1 py-1 aria-disabled:cursor-not-allowed"
                >
                  <span
                    className={
                      'relative rounded-full p-[3px] ' + (on ? 'bg-selection-border' : 'bg-border')
                    }
                  >
                    <span className="block rounded-full bg-canvas p-[2px]">
                      <PersonaAvatar id={id} size={64} />
                    </span>
                    <span
                      aria-hidden
                      className={
                        'absolute -top-1 -right-1 grid size-6 place-items-center rounded-full border-2 ' +
                        (on
                          ? 'border-canvas bg-accent text-on-accent'
                          : 'border-muted bg-canvas text-transparent')
                      }
                    >
                      <Check size={14} strokeWidth={3} />
                    </span>
                  </span>
                  <span className={'text-[15px] ' + (on ? 'font-semibold' : '')}>{ui.label}</span>
                </button>
                <Details
                  persona={byId.get(id)}
                  onAsk={onAskDirectly && !standard ? () => onAskDirectly(id) : undefined}
                />
              </div>
            )
          })}
        </div>
        {edges.left && (
          <button
            type="button"
            aria-label="Scroll perspectives left"
            onClick={() => scrollBy(-240)}
            className="absolute top-1/2 left-0 grid size-10 -translate-y-1/2 place-items-center rounded-full border border-border bg-surface shadow"
          >
            <ChevronLeft aria-hidden size={18} />
          </button>
        )}
        {edges.right && (
          <button
            type="button"
            aria-label="Scroll perspectives right"
            onClick={() => scrollBy(240)}
            className="absolute top-1/2 right-0 grid size-10 -translate-y-1/2 place-items-center rounded-full border border-border bg-surface shadow"
          >
            <ChevronRight aria-hidden size={18} />
          </button>
        )}
      </div>
      {notice && (
        <p role="status" className="mt-1 text-[14px] text-warning">
          {notice}
        </p>
      )}
    </section>
  )
}
