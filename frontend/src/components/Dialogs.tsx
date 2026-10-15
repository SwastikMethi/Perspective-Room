// One host renders every confirmation/prompt/choice dialog; callers await a promise. Radix Dialog
// traps focus; useReturnFocus sends it back to the opener on close.
import { Dialog } from 'radix-ui'
import { type ReactNode, useEffect, useState } from 'react'
import { create } from 'zustand'
import { useReturnFocus } from './focus'

type Request =
  | {
      kind: 'confirm'
      title: string
      body: ReactNode
      confirmLabel: string
      danger?: boolean
      resolve: (ok: boolean) => void
    }
  | {
      kind: 'prompt'
      title: string
      label: string
      initial: string
      confirmLabel: string
      maxLength: number
      multiline?: boolean
      resolve: (value: string | null) => void
    }
  | {
      kind: 'choose'
      title: string
      body?: ReactNode
      options: { value: string; label: string }[]
      initial: string
      confirmLabel: string
      resolve: (value: string | null) => void
    }

const useDialogStore = create<{ current: Request | null }>(() => ({ current: null }))

function open<T>(make: (resolve: (v: T) => void) => Request): Promise<T> {
  return new Promise((resolve) => useDialogStore.setState({ current: make(resolve) }))
}

export const dialogs = {
  confirm: (o: { title: string; body: ReactNode; confirmLabel: string; danger?: boolean }) =>
    open<boolean>((resolve) => ({ kind: 'confirm', ...o, resolve })),
  prompt: (o: {
    title: string
    label: string
    initial?: string
    confirmLabel: string
    maxLength: number
    multiline?: boolean
  }) => open<string | null>((resolve) => ({ kind: 'prompt', initial: '', ...o, resolve })),
  choose: (o: {
    title: string
    body?: ReactNode
    options: { value: string; label: string }[]
    initial: string
    confirmLabel: string
  }) => open<string | null>((resolve) => ({ kind: 'choose', ...o, resolve })),
}

const button =
  'inline-flex min-h-10 items-center justify-center rounded-control px-4 font-medium disabled:opacity-60'
export const primaryButton = `${button} bg-accent text-on-accent hover:bg-accent-hover`
export const secondaryButton = `${button} border border-border text-text hover:bg-surface-subtle`
export const dangerButton = `${button} border border-danger text-danger hover:bg-surface-subtle`

export function DialogFrame({
  open,
  onOpenChange,
  title,
  children,
  description,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description?: ReactNode
  children: ReactNode
}) {
  const returnFocus = useReturnFocus(open)
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50" />
        <Dialog.Content
          onCloseAutoFocus={returnFocus}
          className="fixed top-1/2 left-1/2 z-50 max-h-[85dvh] w-[min(480px,calc(100vw-32px))] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-dialog border border-border bg-surface p-6 text-text shadow-xl"
        >
          <Dialog.Title className="text-[19px] font-semibold">{title}</Dialog.Title>
          <Dialog.Description asChild={typeof description !== 'string'}>
            {description ? (
              <div className="mt-2 text-muted">{description}</div>
            ) : (
              <span className="sr-only">{title}</span>
            )}
          </Dialog.Description>
          {children}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

function PromptBody({
  req,
  done,
}: {
  req: Extract<Request, { kind: 'prompt' }>
  done: () => void
}) {
  const [value, setValue] = useState(req.initial)
  const trimmed = value.trim()
  const Field = req.multiline ? 'textarea' : 'input'
  return (
    <form
      className="mt-4"
      onSubmit={(e) => {
        e.preventDefault()
        if (!trimmed) return
        req.resolve(trimmed)
        done()
      }}
    >
      <label htmlFor="dialog-field" className="text-[13px] text-muted">
        {req.label}
      </label>
      <Field
        id="dialog-field"
        autoFocus
        value={value}
        maxLength={req.maxLength}
        onChange={(e) => setValue(e.target.value)}
        className="mt-1 w-full rounded-control border border-border bg-canvas px-3 py-2 text-text"
        rows={req.multiline ? 3 : undefined}
      />
      <p className="mt-1 text-[13px] text-muted">
        {trimmed.length}/{req.maxLength}
      </p>
      <div className="mt-4 flex justify-end gap-2">
        <Dialog.Close className={secondaryButton}>Cancel</Dialog.Close>
        <button type="submit" disabled={!trimmed} className={primaryButton}>
          {req.confirmLabel}
        </button>
      </div>
    </form>
  )
}

function ChooseBody({
  req,
  done,
}: {
  req: Extract<Request, { kind: 'choose' }>
  done: () => void
}) {
  const [value, setValue] = useState(req.initial)
  return (
    <form
      className="mt-4"
      onSubmit={(e) => {
        e.preventDefault()
        req.resolve(value)
        done()
      }}
    >
      <fieldset className="flex max-h-72 flex-col gap-1 overflow-y-auto">
        <legend className="sr-only">{req.title}</legend>
        {req.options.map((o) => (
          <label
            key={o.value}
            className="flex min-h-10 cursor-pointer items-center gap-3 rounded-control px-2 hover:bg-surface-subtle"
          >
            <input
              type="radio"
              name="dialog-choice"
              value={o.value}
              checked={value === o.value}
              onChange={() => setValue(o.value)}
              className="size-4 accent-[var(--accent)]"
            />
            <span className="truncate">{o.label}</span>
          </label>
        ))}
      </fieldset>
      <div className="mt-4 flex justify-end gap-2">
        <Dialog.Close className={secondaryButton}>Cancel</Dialog.Close>
        <button type="submit" className={primaryButton}>
          {req.confirmLabel}
        </button>
      </div>
    </form>
  )
}

export function DialogHost() {
  const current = useDialogStore((s) => s.current)
  const done = () => useDialogStore.setState({ current: null })
  const cancel = () => {
    if (!current) return
    if (current.kind === 'confirm') current.resolve(false)
    else current.resolve(null)
    done()
  }
  if (!current) return null
  return (
    <DialogFrame
      open
      onOpenChange={(o) => !o && cancel()}
      title={current.title}
      description={
        current.kind === 'confirm'
          ? current.body
          : current.kind === 'choose'
            ? current.body
            : undefined
      }
    >
      {current.kind === 'confirm' && (
        <div className="mt-6 flex justify-end gap-2">
          <Dialog.Close className={secondaryButton}>Cancel</Dialog.Close>
          <button
            type="button"
            autoFocus
            className={current.danger ? dangerButton : primaryButton}
            onClick={() => {
              current.resolve(true)
              done()
            }}
          >
            {current.confirmLabel}
          </button>
        </div>
      )}
      {current.kind === 'prompt' && <PromptBody req={current} done={done} />}
      {current.kind === 'choose' && <ChooseBody req={current} done={done} />}
    </DialogFrame>
  )
}

// ---------- notices: polite, transient status lines (never the only record of an error) ----------

interface Notice {
  id: number
  text: string
  tone: 'info' | 'error'
}
const useNotices = create<{ items: Notice[] }>(() => ({ items: [] }))
let seq = 0

export function notify(text: string, tone: Notice['tone'] = 'info') {
  const id = ++seq
  useNotices.setState((s) => ({ items: [...s.items.slice(-2), { id, text, tone }] }))
  setTimeout(
    () => useNotices.setState((s) => ({ items: s.items.filter((n) => n.id !== id) })),
    tone === 'error' ? 8000 : 4000,
  )
}

export function NoticeHost() {
  const items = useNotices((s) => s.items)
  const [mounted, setMounted] = useState(false)
  useEffect(() => setMounted(true), [])
  return (
    <div
      aria-live="polite"
      className="pointer-events-none fixed right-4 bottom-4 z-[60] flex w-[min(380px,calc(100vw-32px))] flex-col gap-2"
    >
      {mounted &&
        items.map((n) => (
          <p
            key={n.id}
            role={n.tone === 'error' ? 'alert' : 'status'}
            className={
              'pointer-events-auto rounded-card border bg-surface px-4 py-3 text-sm shadow-lg ' +
              (n.tone === 'error' ? 'border-danger text-text' : 'border-border text-text')
            }
          >
            {n.text}
          </p>
        ))}
    </div>
  )
}
