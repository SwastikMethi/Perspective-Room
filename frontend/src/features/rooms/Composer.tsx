import { ArrowUp, Plus, Square, X } from 'lucide-react'
import { DropdownMenu } from 'radix-ui'
import { type KeyboardEvent, useEffect, useRef, useState } from 'react'
import type { Schemas } from '../../api/client'
import { StorageNotice } from '../../components/StorageNotice'
import { PERSONA_UI, ROSTER, shortLabel } from '../../lib/personas'
import { type Draft, useDrafts } from '../../stores/drafts'
import { menuContent, menuItem } from '../workspace/ChatRow'
import { defaultControl } from './send'

type Control = Schemas['TurnControl']
type Move = NonNullable<Control['move_override']>

const MOVES: { value: Move; label: string; hint: string }[] = [
  { value: 'explore', label: 'Explore', hint: 'open new directions' },
  { value: 'challenge', label: 'Challenge', hint: 'test the weakest point' },
  { value: 'expand', label: 'Expand', hint: 'go deeper on one idea' },
  { value: 'combine', label: 'Combine', hint: 'merge two or more ideas' },
]

export function controlFor(draft: Draft | undefined): Control {
  return { ...defaultControl(), ...(draft?.control ?? {}) } as Control
}

const select =
  'min-h-10 rounded-control border border-border bg-surface px-2 text-[14px] text-text disabled:opacity-60'

export interface ComposerProps {
  draftKey: string
  personas: Schemas['Persona'][]
  selected: string[]
  standard: boolean
  running: boolean
  disabledReason?: string | null
  ideas: Schemas['IdeaCard'][]
  replyLabel?: (messageId: string) => string | null
  onSend: (text: string, control: Control) => Promise<void>
  onStop: () => void
  onTarget: (personaId: string) => Promise<void> | void
  onAddConstraint?: () => void
  registerFocus?: (focus: () => void) => void
}

/** Structured controls change request data, never the visible text (doc 03). */
export function Composer(props: ComposerProps) {
  const { draftKey, personas, selected, standard, running, disabledReason, ideas } = props
  const draft = useDrafts((s) => s.drafts[draftKey])
  const setDraft = useDrafts((s) => s.set)
  const text = draft?.text ?? ''
  const control = controlFor(draft)
  const refs = control.idea_card_ids
  const box = useRef<HTMLTextAreaElement>(null)
  const [busy, setBusy] = useState(false)
  const [mention, setMention] = useState<{ start: number; query: string; index: number } | null>(
    null,
  )
  const names = new Map(personas.map((p) => [p.id, p.display_name]))
  const blocked = Boolean(disabledReason)

  useEffect(() => props.registerFocus?.(() => box.current?.focus()), [props])

  const patch = (c: Partial<Control>) =>
    setDraft(draftKey, { control: { ...(draft?.control ?? {}), ...c } })
  const reset = () =>
    setDraft(draftKey, { control: { research_override: control.research_override } })

  const matches = mention
    ? ROSTER.filter((id) =>
        `${PERSONA_UI[id].label} ${names.get(id) ?? ''}`
          .toLowerCase()
          .includes(mention.query.toLowerCase()),
      )
    : []

  const chooseMention = async (id: string) => {
    if (!mention) return
    const next = text.slice(0, mention.start) + text.slice(mention.start + 1 + mention.query.length)
    setDraft(draftKey, { text: next })
    setMention(null)
    await props.onTarget(id)
  }

  const send = async () => {
    if (!text.trim() || running || busy || blocked) return
    setBusy(true)
    try {
      await props.onSend(text, control)
    } catch {
      // The room reports the error; the draft text and options stay as they were.
    } finally {
      setBusy(false)
    }
  }

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.nativeEvent.isComposing || e.keyCode === 229) return // IME composition: never send
    if (mention && matches.length) {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault()
        const d = e.key === 'ArrowDown' ? 1 : -1
        setMention({ ...mention, index: (mention.index + d + matches.length) % matches.length })
        return
      }
      if (e.key === 'Enter' || e.key === 'Tab') {
        e.preventDefault()
        void chooseMention(matches[mention.index % matches.length])
        return
      }
      if (e.key === 'Escape') {
        setMention(null)
        return
      }
    }
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      void send()
    }
  }

  const onChange = (value: string, caret: number) => {
    setDraft(draftKey, { text: value })
    const before = value.slice(0, caret)
    const m = !standard && /(^|\s)@([\w-]{0,20})$/.exec(before)
    setMention(m ? { start: caret - m[2].length - 1, query: m[2], index: 0 } : null)
  }

  const chips: { key: string; label: string; clear: () => void }[] = []
  if (control.audience === 'person' && control.target_persona_id)
    chips.push({
      key: 'target',
      label: selected.includes(control.target_persona_id)
        ? `To ${shortLabel(control.target_persona_id)}`
        : `To ${shortLabel(control.target_persona_id)} — not in this room; reselect`,
      clear: () => patch({ audience: 'auto', target_persona_id: null }),
    })
  if (control.audience === 'panel')
    chips.push({
      key: 'panel',
      label: 'Everyone selected',
      clear: () => patch({ audience: 'auto' }),
    })
  if (control.move_override)
    chips.push({
      key: 'move',
      label: `Move: ${MOVES.find((m) => m.value === control.move_override)?.label}`,
      clear: () => patch({ move_override: null }),
    })
  if (control.reply_to_message_id)
    chips.push({
      key: 'reply',
      label: props.replyLabel?.(control.reply_to_message_id) ?? 'Replying to a message',
      clear: () => patch({ reply_to_message_id: null }),
    })
  for (const id of refs) {
    const card = ideas.find((c) => c.id === id)
    chips.push({
      key: `ref-${id}`,
      label: card ? `Idea: ${card.title}` : 'A saved idea that no longer exists — reselect',
      clear: () => patch({ idea_card_ids: refs.filter((r) => r !== id) }),
    })
  }
  const combineShort =
    control.move_override === 'combine' && refs.length + (control.reply_to_message_id ? 1 : 0) < 2

  const target =
    control.audience === 'person' && control.target_persona_id
      ? control.target_persona_id
      : control.audience === 'panel'
        ? 'panel'
        : 'auto'

  return (
    <div className="sticky bottom-0 z-10 bg-gradient-to-t from-canvas from-70% to-transparent pt-4 pb-[max(12px,env(safe-area-inset-bottom))]">
      {chips.length > 0 && (
        <ul aria-label="Turn options" className="mb-2 flex flex-wrap gap-2">
          {chips.map((c) => (
            <li
              key={c.key}
              className="inline-flex max-w-full items-center gap-1 rounded-control border border-selection-border bg-selection-surface py-1 pr-1 pl-3 text-[14px]"
            >
              <span className="truncate">{c.label}</span>
              <button
                type="button"
                aria-label={`Remove: ${c.label}`}
                onClick={c.clear}
                className="grid size-7 place-items-center rounded-control hover:bg-surface-subtle"
              >
                <X aria-hidden size={14} />
              </button>
            </li>
          ))}
          <li>
            <button
              type="button"
              onClick={reset}
              className="min-h-9 px-2 text-[13px] text-muted underline"
            >
              Clear options
            </button>
          </li>
        </ul>
      )}
      {combineShort && (
        <p className="mb-2 text-[13px] text-warning">
          Combine needs at least two ideas: reference saved ideas from the plus menu, or reply to a
          message and add one idea.
        </p>
      )}
      <form
        onSubmit={(e) => {
          e.preventDefault()
          void send()
        }}
        className="relative flex flex-wrap items-end gap-2 rounded-card border border-border bg-surface p-2 shadow-sm focus-within:border-selection-border sm:flex-nowrap"
      >
        <DropdownMenu.Root>
          <DropdownMenu.Trigger
            aria-label="Add context"
            disabled={blocked}
            className="grid size-11 shrink-0 place-items-center rounded-full border border-border text-text hover:bg-surface-subtle disabled:opacity-60"
          >
            <Plus aria-hidden size={22} />
          </DropdownMenu.Trigger>
          <DropdownMenu.Portal>
            <DropdownMenu.Content side="top" align="start" sideOffset={6} className={menuContent}>
              <DropdownMenu.Label className="px-3 pt-1 pb-1 text-[12px] text-muted">
                Reference saved ideas
              </DropdownMenu.Label>
              {ideas.length === 0 && (
                <p className="px-3 pb-2 text-[13px] text-muted">
                  Save a reply with its bookmark first.
                </p>
              )}
              {ideas.map((c) => (
                <DropdownMenu.CheckboxItem
                  key={c.id}
                  className={menuItem}
                  checked={refs.includes(c.id)}
                  onSelect={(e) => e.preventDefault()}
                  onCheckedChange={(on) =>
                    patch({ idea_card_ids: on ? [...refs, c.id] : refs.filter((r) => r !== c.id) })
                  }
                >
                  <span className="w-4">{refs.includes(c.id) ? '✓' : ''}</span>
                  <span className="truncate">{c.title}</span>
                </DropdownMenu.CheckboxItem>
              ))}
              <DropdownMenu.Separator className="my-1 h-px bg-border" />
              {props.onAddConstraint && (
                <DropdownMenu.Item className={menuItem} onSelect={props.onAddConstraint}>
                  Add a constraint to the brief…
                </DropdownMenu.Item>
              )}
              <DropdownMenu.Label className="px-3 pt-1 pb-1 text-[12px] text-muted">
                Choose a move
              </DropdownMenu.Label>
              {MOVES.map((m) => (
                <DropdownMenu.Item
                  key={m.value}
                  className={menuItem}
                  onSelect={() =>
                    patch({ move_override: control.move_override === m.value ? null : m.value })
                  }
                >
                  <span className="w-4">{control.move_override === m.value ? '✓' : ''}</span>
                  {m.label}
                  <span className="text-[13px] text-muted">— {m.hint}</span>
                </DropdownMenu.Item>
              ))}
            </DropdownMenu.Content>
          </DropdownMenu.Portal>
        </DropdownMenu.Root>
        <div className="relative order-first min-w-0 basis-full sm:order-none sm:basis-auto sm:flex-1">
          <label htmlFor={`composer-${draftKey}`} className="sr-only">
            Message
          </label>
          <textarea
            id={`composer-${draftKey}`}
            ref={box}
            rows={1}
            value={text}
            disabled={blocked}
            maxLength={16000}
            aria-describedby={`composer-hint-${draftKey}`}
            role={standard ? undefined : 'combobox'}
            aria-autocomplete={standard ? undefined : 'list'}
            aria-activedescendant={
              mention && matches.length
                ? `mention-${draftKey}-${matches[mention.index % matches.length]}`
                : undefined
            }
            aria-expanded={mention ? matches.length > 0 : undefined}
            aria-controls={mention ? `mentions-${draftKey}` : undefined}
            onChange={(e) => onChange(e.target.value, e.target.selectionStart)}
            onKeyDown={onKeyDown}
            placeholder={disabledReason ?? 'Bring another thought to the room…'}
            className="field-sizing-content max-h-60 min-h-11 w-full resize-none bg-transparent px-2 py-2.5 text-text outline-none placeholder:text-muted"
          />
          <span id={`composer-hint-${draftKey}`} className="sr-only">
            Enter sends. Shift+Enter adds a new line. Type @ to address one perspective.
          </span>
          {mention && matches.length > 0 && (
            <ul
              id={`mentions-${draftKey}`}
              role="listbox"
              aria-label="Address a perspective"
              className="absolute bottom-full left-0 z-20 mb-2 w-64 rounded-card border border-border bg-surface p-1 shadow-xl"
            >
              {matches.map((id, i) => (
                <li
                  key={id}
                  id={`mention-${draftKey}-${id}`}
                  role="option"
                  aria-selected={i === mention.index % matches.length}
                  onMouseDown={(e) => {
                    e.preventDefault()
                    void chooseMention(id)
                  }}
                  className="flex min-h-10 cursor-pointer items-center gap-2 rounded-control px-3 aria-selected:bg-surface-subtle"
                >
                  <span
                    aria-hidden
                    className="size-2.5 rounded-full"
                    style={{ background: PERSONA_UI[id].accent }}
                  />
                  {PERSONA_UI[id].label}
                  {!selected.includes(id) && (
                    <span className="ml-auto text-[12px] text-muted">not in room</span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
        {!standard && (
          <label className="flex items-center">
            <span className="sr-only">Who answers</span>
            <select
              className={select}
              value={target}
              disabled={blocked}
              onChange={async (e) => {
                const v = e.target.value
                if (v === 'auto') patch({ audience: 'auto', target_persona_id: null })
                else if (v === 'panel') patch({ audience: 'panel', target_persona_id: null })
                else await props.onTarget(v)
              }}
            >
              <option value="auto">To: Auto</option>
              <option value="panel">To: Everyone selected</option>
              {selected.map((id) => (
                <option key={id} value={id}>
                  To: {shortLabel(id)}
                </option>
              ))}
              {target !== 'auto' && target !== 'panel' && !selected.includes(target as never) && (
                <option value={target}>To: {shortLabel(target)} (not in this room)</option>
              )}
            </select>
          </label>
        )}
        <label className="flex items-center">
          <span className="sr-only">Research</span>
          <select
            className={select}
            value={control.research_override}
            disabled={blocked}
            onChange={(e) =>
              patch({ research_override: e.target.value as Control['research_override'] })
            }
          >
            <option value="auto">Research: Auto</option>
            <option value="off">Research: Off</option>
            <option value="force">Research: Force</option>
          </select>
        </label>
        {running ? (
          <button
            type="button"
            onClick={props.onStop}
            className="inline-flex min-h-11 shrink-0 items-center gap-2 rounded-control border border-border px-4 font-medium hover:bg-surface-subtle"
          >
            <Square aria-hidden size={14} fill="currentColor" /> Stop
          </button>
        ) : (
          <button
            type="submit"
            disabled={busy || blocked || !text.trim() || combineShort}
            aria-label="Send"
            className="grid size-11 shrink-0 place-items-center rounded-control bg-accent text-on-accent hover:bg-accent-hover disabled:opacity-60"
          >
            <ArrowUp aria-hidden size={22} strokeWidth={2.5} />
          </button>
        )}
      </form>
      <div className="mt-1 flex flex-wrap justify-between gap-2 px-1 text-[13px] text-muted">
        <StorageNotice />
        <span className="ml-auto max-sm:hidden">
          Enter to send · Shift+Enter for a new line · @ to address one
        </span>
      </div>
    </div>
  )
}
