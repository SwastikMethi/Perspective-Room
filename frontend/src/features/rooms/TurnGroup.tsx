import {
  Bookmark,
  BookmarkCheck,
  ChevronDown,
  ChevronUp,
  Copy,
  CornerDownRight,
  MessageCircleQuestion,
  MoreHorizontal,
  Reply,
  Swords,
  ThumbsUp,
} from 'lucide-react'
import { DropdownMenu, Popover } from 'radix-ui'
import { createContext, type ReactNode, useContext, useEffect, useRef, useState } from 'react'
import type { Schemas } from '../../api/client'
import { notify } from '../../components/Dialogs'
import { MarkdownText } from '../../components/MarkdownText'
import { PersonaAvatar } from '../../components/PersonaAvatar'
import { PERSONA_UI, shortLabel } from '../../lib/personas'
import { MenuItem, menuContent } from '../workspace/ChatRow'
import { copyText, SECTION_LABELS, warningText } from './copy'
import { columnsFor, numberSources, type TurnGroupData } from './grouping'
import type { RoomActions } from './roomActions'
import { useRoomUi } from './roomUi'

type Message = Schemas['Message']

export interface RoomData {
  session: Schemas['Session']
  names: Map<string, string>
  sources: Map<string, Schemas['Source']>
  saved: Map<string, Schemas['IdeaCard']>
  actions: RoomActions
  running: boolean
}
export const RoomContext = createContext<RoomData | null>(null)
const useRoom = () => useContext(RoomContext)!

export function useContentWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  const [width, setWidth] = useState(0)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    setWidth(el.clientWidth)
    if (typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  return { ref, width }
}

const KIND_LABEL: Record<string, string> = {
  observation: 'Observation',
  suggestion: 'Suggestion',
  question: 'Question',
  assumption: 'Assumption',
  fact: 'Sourced fact',
  limitation: 'Limitation',
}

const iconButton =
  'inline-flex min-h-9 items-center gap-1.5 rounded-control px-2 text-[13px] text-muted hover:bg-surface-subtle hover:text-text'

function Citations({ ids, numbers }: { ids: string[]; numbers: Map<string, number> }) {
  const open = useRoomUi((s) => s.openDrawer)
  const { sources } = useRoom()
  const known = ids.filter((id) => sources.has(id) || numbers.has(id))
  if (!known.length) return null
  return (
    <span className="ml-1 inline-flex gap-1 align-baseline">
      {known.map((id) => (
        <button
          key={id}
          type="button"
          onClick={() => open('sources', id)}
          aria-label={`Source ${numbers.get(id)}: ${sources.get(id)?.title ?? 'open in Sources'}`}
          className="rounded-[6px] border border-border px-1.5 text-[12px] leading-5 text-text hover:border-selection-border"
        >
          {numbers.get(id)}
        </button>
      ))}
    </span>
  )
}

function FeedbackButton({ message }: { message: Message }) {
  const { actions } = useRoom()
  const [labels, setLabels] = useState<Schemas['FeedbackCreate']['labels']>([])
  const [note, setNote] = useState('')
  const options = [
    ['useful', 'Useful'],
    ['new_perspective', 'A new perspective'],
    ['repetitive', 'Repetitive'],
    ['off_character', 'Off character'],
  ] as const
  return (
    <Popover.Root>
      <Popover.Trigger className={iconButton}>
        <ThumbsUp aria-hidden size={15} /> Feedback
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          sideOffset={6}
          className="z-50 w-72 rounded-card border border-border bg-surface p-4 text-text shadow-xl"
        >
          <form
            onSubmit={(e) => {
              e.preventDefault()
              void actions.sendFeedback(message, labels, note.trim())
            }}
          >
            <fieldset>
              <legend className="font-medium">How was this reply?</legend>
              {options.map(([value, label]) => (
                <label key={value} className="mt-1 flex min-h-9 items-center gap-2">
                  <input
                    type="checkbox"
                    checked={labels.includes(value)}
                    onChange={(e) =>
                      setLabels((l) =>
                        e.target.checked ? [...l, value] : l.filter((x) => x !== value),
                      )
                    }
                    className="size-4 accent-[var(--accent)]"
                  />
                  {label}
                </label>
              ))}
            </fieldset>
            <label htmlFor={`fb-${message.id}`} className="mt-2 block text-[13px] text-muted">
              Note (optional)
            </label>
            <textarea
              id={`fb-${message.id}`}
              value={note}
              maxLength={4000}
              onChange={(e) => setNote(e.target.value)}
              rows={2}
              className="mt-1 w-full rounded-control border border-border bg-canvas p-2"
            />
            <Popover.Close
              type="submit"
              className="mt-2 min-h-10 rounded-control bg-accent px-3 font-medium text-on-accent"
            >
              Save feedback
            </Popover.Close>
          </form>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
}

function copyToClipboard(text: string) {
  void navigator.clipboard.writeText(text).then(
    () => notify('Copied.'),
    () => notify('Copy failed — your browser blocked clipboard access.', 'error'),
  )
}

function ContributionCard({
  message,
  user,
  numbers,
  expanded,
}: {
  message: Message
  user: Message | null
  numbers: Map<string, number>
  expanded: boolean
}) {
  const room = useRoom()
  const highlight = useRoomUi((s) => s.highlight)
  const c = message.contribution!
  const pid = message.persona_id
  const label = pid ? shortLabel(pid) : 'Assistant'
  const speaker = pid ? (room.names.get(pid) ?? label) : 'Assistant'
  const saved = room.saved.get(message.id)
  const cited = [...new Set(c.blocks.flatMap((b) => b.source_ids))]
  const first = c.blocks[0]
  const archived = room.session.is_archived
  const sourcesForCopy = new Map(
    [...room.sources].map(([id, s]) => [id, { title: s.title, url: s.url }]),
  )
  return (
    <article
      id={`m-${message.id}`}
      data-testid="contribution"
      data-persona={pid ?? 'assistant'}
      aria-labelledby={`h-${message.id}`}
      className={
        'group flex min-w-0 flex-col rounded-card border bg-surface p-5 ' +
        (highlight === message.id
          ? 'border-selection-border ring-2 ring-selection-border'
          : 'border-border')
      }
    >
      <header className="flex items-center gap-3">
        {pid ? <PersonaAvatar id={pid} size={40} /> : null}
        <span className="flex min-w-0 flex-1 items-center gap-2 text-[13px] font-medium tracking-[0.12em] text-muted uppercase">
          {pid && (
            <span
              aria-hidden
              className="size-2.5 shrink-0 rounded-full"
              style={{ background: PERSONA_UI[pid]?.accent }}
            />
          )}
          <span className="truncate" title={speaker}>
            The {label}
          </span>
        </span>
        {!archived && (
          <button
            type="button"
            aria-pressed={Boolean(saved)}
            aria-label={saved ? `Remove saved idea “${c.headline}”` : `Save idea “${c.headline}”`}
            onClick={() => void room.actions.toggleSaved(message, saved)}
            className="grid size-9 shrink-0 place-items-center rounded-control text-muted hover:text-text aria-pressed:text-text"
          >
            {saved ? <BookmarkCheck aria-hidden size={20} /> : <Bookmark aria-hidden size={20} />}
          </button>
        )}
      </header>
      <h3
        id={`h-${message.id}`}
        className="mt-3 text-[20px] leading-snug font-semibold [overflow-wrap:anywhere]"
      >
        {c.headline}
      </h3>
      {!expanded ? (
        <div className="mt-2 text-muted">
          {first && (
            <div className="line-clamp-4">
              <MarkdownText text={first.text} />
            </div>
          )}
          {cited.length > 0 && (
            <button
              type="button"
              onClick={() => useRoomUi.getState().openDrawer('sources', cited[0])}
              className="mt-2 text-[13px] text-text underline underline-offset-2"
            >
              {cited.length} {cited.length === 1 ? 'source' : 'sources'}
            </button>
          )}
        </div>
      ) : (
        <div className="mt-2 max-w-[var(--message-measure)] space-y-3">
          {c.blocks.map((b, i) => (
            <div key={i}>
              <p className="text-[12px] font-medium text-muted">{KIND_LABEL[b.kind] ?? b.kind}</p>
              <div className="flex flex-wrap items-baseline">
                <div className="min-w-0 flex-1">
                  <MarkdownText text={b.text} />
                </div>
                <Citations ids={b.source_ids} numbers={numbers} />
              </div>
            </div>
          ))}
          <p className="text-[14px] text-muted">
            <span className="font-medium text-text">New angle:</span> {c.new_angle}
          </p>
          {c.next_question && (
            <p className="text-[14px] text-muted">
              <span className="font-medium text-text">Next question:</span> {c.next_question}
            </p>
          )}
        </div>
      )}
      {message.warning_codes.length > 0 && (
        <ul className="mt-2 text-[13px] text-warning">
          {message.warning_codes.map((w) => (
            <li key={w}>{warningText(w)}</li>
          ))}
        </ul>
      )}
      <div className="mt-auto flex flex-wrap items-center gap-1 pt-3 opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 [@media(pointer:coarse)]:opacity-100">
        <button
          type="button"
          className={iconButton}
          onClick={() => copyToClipboard(copyText(message, speaker, sourcesForCopy))}
        >
          <Copy aria-hidden size={15} /> Copy
        </button>
        {!archived && (
          <>
            <button
              type="button"
              className={iconButton}
              disabled={room.running}
              onClick={() => void room.actions.setIntent('reply', message)}
            >
              <Reply aria-hidden size={15} /> Reply
            </button>
            <button
              type="button"
              className={iconButton}
              disabled={room.running}
              onClick={() => void room.actions.setIntent('ask', message)}
            >
              <MessageCircleQuestion aria-hidden size={15} /> Ask more
            </button>
            <button
              type="button"
              className={iconButton}
              disabled={room.running}
              onClick={() => void room.actions.setIntent('challenge', message)}
            >
              <Swords aria-hidden size={15} /> Challenge
            </button>
            <FeedbackButton message={message} />
            <DropdownMenu.Root>
              <DropdownMenu.Trigger
                aria-label={`More actions for ${c.headline}`}
                className={iconButton}
              >
                <MoreHorizontal aria-hidden size={16} />
              </DropdownMenu.Trigger>
              <DropdownMenu.Portal>
                <DropdownMenu.Content align="end" sideOffset={4} className={menuContent}>
                  <MenuItem
                    disabled={room.running}
                    onSelect={() => void room.actions.forkHere(message)}
                  >
                    Fork here — new chat up to this reply
                  </MenuItem>
                  {user && (
                    <MenuItem
                      disabled={room.running}
                      onSelect={() => void room.actions.regenerate(user)}
                    >
                      Regenerate round — in a new branch
                    </MenuItem>
                  )}
                </DropdownMenu.Content>
              </DropdownMenu.Portal>
            </DropdownMenu.Root>
          </>
        )}
      </div>
    </article>
  )
}

function SummaryCard({ message, numbers }: { message: Message; numbers: Map<string, number> }) {
  const highlight = useRoomUi((s) => s.highlight)
  return (
    <article
      id={`m-${message.id}`}
      data-testid="summary"
      className={
        'rounded-card border bg-surface p-5 ' +
        (highlight === message.id
          ? 'border-selection-border ring-2 ring-selection-border'
          : 'border-border')
      }
    >
      <h3 className="text-[13px] font-medium tracking-[0.12em] text-muted uppercase">Summary</h3>
      <div className="mt-3 grid gap-4 md:grid-cols-2">
        {message.summary!.sections.map((s) => (
          <section key={s.kind}>
            <h4 className="font-semibold">{SECTION_LABELS[s.kind] ?? s.kind}</h4>
            <ul className="mt-1 list-disc space-y-1 pl-5 text-[15px]">
              {s.items.map((i, n) => (
                <li key={n}>
                  {i.text}
                  <Citations ids={i.source_ids} numbers={numbers} />
                  {i.source_message_ids.length > 0 && (
                    <span className="ml-1">
                      {i.source_message_ids.map((id) => (
                        <a
                          key={id}
                          href={`#m-${id}`}
                          onClick={() => useRoomUi.setState({ highlight: id })}
                          className="ml-1 text-[12px] text-muted underline"
                        >
                          reply
                        </a>
                      ))}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </article>
  )
}

const LONG_USER_TEXT = 1200

function UserMessage({ message, first }: { message: Message; first: boolean }) {
  const room = useRoom()
  const highlight = useRoomUi((s) => s.highlight)
  const [open, setOpen] = useState(false)
  const text = message.text ?? ''
  const long = text.length > LONG_USER_TEXT || text.split('\n').length > 14
  return (
    <div
      id={`m-${message.id}`}
      data-testid="user-message"
      className={
        'group rounded-card ' + (highlight === message.id ? 'ring-2 ring-selection-border' : '')
      }
    >
      <div className="flex items-center gap-2">
        <p className="text-[13px] font-medium tracking-[0.12em] text-muted uppercase">
          {first ? 'Your idea' : 'You'}
        </p>
        <div className="ml-auto flex opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 [@media(pointer:coarse)]:opacity-100">
          <button
            type="button"
            className={iconButton}
            onClick={() => copyToClipboard(`You\n\n${text}`)}
          >
            <Copy aria-hidden size={15} /> Copy
          </button>
          {!room.session.is_archived && (
            <DropdownMenu.Root>
              <DropdownMenu.Trigger
                aria-label="More actions for your message"
                className={iconButton}
              >
                <MoreHorizontal aria-hidden size={16} />
              </DropdownMenu.Trigger>
              <DropdownMenu.Portal>
                <DropdownMenu.Content align="end" sideOffset={4} className={menuContent}>
                  <MenuItem
                    disabled={room.running}
                    onSelect={() => void room.actions.editMessage(message)}
                  >
                    Edit message — send as new branch
                  </MenuItem>
                  <MenuItem
                    disabled={room.running}
                    onSelect={() => void room.actions.regenerate(message)}
                  >
                    Regenerate round — in a new branch
                  </MenuItem>
                </DropdownMenu.Content>
              </DropdownMenu.Portal>
            </DropdownMenu.Root>
          )}
        </div>
      </div>
      <div
        className={
          'mt-1 max-w-[var(--message-measure)] whitespace-pre-wrap [overflow-wrap:anywhere] ' +
          (first ? 'text-[24px] leading-snug font-medium' : 'text-[17px]') +
          (long && !open ? ' line-clamp-[10]' : '')
        }
      >
        {text}
      </div>
      {long && (
        <button
          type="button"
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
          className="mt-1 text-[14px] text-muted underline underline-offset-2 hover:text-text"
        >
          {open ? 'Show less' : 'Show full message'}
        </button>
      )}
    </div>
  )
}

export function TurnGroup({
  group,
  first,
  footer,
}: {
  group: TurnGroupData
  first: boolean
  footer?: ReactNode
}) {
  const expanded = useRoomUi((s) => Boolean(s.expanded[group.key]))
  const toggle = useRoomUi((s) => s.toggleGroup)
  const { ref, width } = useContentWidth<HTMLDivElement>()
  const cards = group.replies.filter((m) => m.contribution)
  const others = group.replies.filter((m) => !m.contribution)
  const numbers = numberSources(group.replies)
  const columns = expanded ? 1 : columnsFor(width)
  const expandable = cards.some(
    (m) => m.contribution!.blocks.length > 1 || m.contribution!.blocks[0]?.text.length > 220,
  )
  return (
    <section aria-label={first ? 'Opening turn' : 'Turn'} className="flex flex-col gap-4">
      {group.user && <UserMessage message={group.user} first={first} />}
      <div
        ref={ref}
        data-columns={columns}
        className="grid gap-4"
        style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}
      >
        {cards.map((m) => (
          <ContributionCard
            key={m.id}
            message={m}
            user={group.user}
            numbers={numbers}
            expanded={expanded}
          />
        ))}
      </div>
      {others.map((m) =>
        m.summary ? (
          <SummaryCard key={m.id} message={m} numbers={numbers} />
        ) : (
          <article
            key={m.id}
            id={`m-${m.id}`}
            data-testid="moderator-message"
            className="rounded-card border border-border bg-surface p-5"
          >
            <p className="flex items-center gap-2 text-[13px] font-medium tracking-[0.12em] text-muted uppercase">
              <CornerDownRight aria-hidden size={14} /> Moderator
            </p>
            <div className="mt-2 max-w-[var(--message-measure)]">
              <MarkdownText text={m.text ?? ''} />
            </div>
          </article>
        ),
      )}
      {expandable && (
        <button
          type="button"
          aria-expanded={expanded}
          onClick={() => toggle(group.key)}
          className="inline-flex min-h-10 items-center gap-1 self-start rounded-control px-2 text-[15px] font-medium hover:bg-surface-subtle"
        >
          {expanded ? <ChevronUp aria-hidden size={18} /> : <ChevronDown aria-hidden size={18} />}
          {expanded ? 'Show compact cards' : 'Read full response'}
        </button>
      )}
      {footer}
    </section>
  )
}
