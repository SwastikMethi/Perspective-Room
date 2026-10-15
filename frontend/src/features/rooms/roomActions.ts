// Actions on messages inside a room. Composer intents change structured request data (doc 03),
// never the visible text; branch actions never mutate the current chat.
import { useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router'
import { ApiError, api, newIdempotencyKey, type Schemas, unwrap } from '../../api/client'
import { keys } from '../../api/queries'
import { dialogs, notify } from '../../components/Dialogs'
import { shortLabel } from '../../lib/personas'
import { useDrafts } from '../../stores/drafts'
import { useRoomUi } from './roomUi'
import { resolvePending } from './pending'
import { discardPending, PendingConflict, sendBranch, TurnRejected, withOperationKey } from './send'

type Message = Schemas['Message']
type PersonaId = Schemas['Session']['selected_persona_ids'][number]
export type Intent = 'reply' | 'ask' | 'challenge'

const errorText = (e: unknown) =>
  e instanceof ApiError ? e.error.message : 'That did not work. Try again.'

export function useRoomActions(session: Schemas['Session'] | undefined) {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const sessionId = session?.id ?? ''

  /** Add an unselected persona before targeting it — never silently (G12). */
  const ensureSelected = async (personaId: string): Promise<boolean> => {
    if (!session || session.selected_persona_ids.includes(personaId as PersonaId)) return true
    const ok = await dialogs.confirm({
      title: `Add ${shortLabel(personaId)} to this room?`,
      body: `${shortLabel(personaId)} is not selected in this chat. Adding them changes who can be asked from now on.`,
      confirmLabel: `Add ${shortLabel(personaId)}`,
    })
    if (!ok) return false
    try {
      const next = await unwrap(
        api.PATCH('/api/v1/sessions/{session_id}', {
          params: { path: { session_id: sessionId } },
          body: {
            expected_version: session.version,
            selected_persona_ids: [...session.selected_persona_ids, personaId as PersonaId],
          },
        }),
      )
      qc.setQueryData(keys.session(sessionId), next)
      return true
    } catch (e) {
      notify(errorText(e), 'error')
      return false
    }
  }

  const setIntent = async (intent: Intent, m: Message) => {
    if (!session) return
    const standard = session.mode === 'standard'
    let control: Partial<Schemas['TurnControl']> = { reply_to_message_id: m.id }
    if (intent === 'challenge')
      control = {
        ...control,
        audience: 'auto',
        target_persona_id: null,
        move_override: 'challenge',
      }
    if (intent === 'ask') {
      if (standard || !m.persona_id)
        control = { ...control, audience: 'auto', target_persona_id: null, move_override: 'expand' }
      else {
        if (!(await ensureSelected(m.persona_id))) return
        control = {
          ...control,
          audience: 'person',
          target_persona_id: m.persona_id,
          move_override: 'expand',
        }
      }
    }
    const current = useDrafts.getState().get(sessionId)?.control ?? {}
    useDrafts.getState().set(sessionId, { control: { ...current, ...control } })
    useRoomUi.getState().focusComposer()
  }

  const target = async (personaId: string) => {
    if (!session || !(await ensureSelected(personaId))) return
    const current = useDrafts.getState().get(sessionId)?.control ?? {}
    useDrafts.getState().set(sessionId, {
      control: { ...current, audience: 'person', target_persona_id: personaId as PersonaId },
    })
    useRoomUi.getState().focusComposer()
  }

  const toggleSaved = async (m: Message, card: Schemas['IdeaCard'] | undefined) => {
    try {
      if (card) {
        if (
          card.note.trim() &&
          !(await dialogs.confirm({
            title: 'Remove this saved idea?',
            body: 'Its note will be removed too.',
            confirmLabel: 'Remove',
            danger: true,
          }))
        )
          return
        await unwrap(
          api.DELETE('/api/v1/idea-cards/{card_id}', { params: { path: { card_id: card.id } } }),
        )
      } else {
        await unwrap(
          api.POST('/api/v1/sessions/{session_id}/idea-cards', {
            params: {
              path: { session_id: sessionId },
              header: { 'Idempotency-Key': newIdempotencyKey() },
            },
            body: {
              message_id: m.id,
              title: (m.contribution?.headline ?? 'Saved idea').slice(0, 120),
              note: '',
              status: 'exploring',
            },
          }),
        )
      }
    } catch (e) {
      notify(errorText(e), 'error')
    } finally {
      await qc.invalidateQueries({ queryKey: keys.ideas(sessionId) })
    }
  }

  const sendFeedback = async (
    m: Message,
    labels: Schemas['FeedbackCreate']['labels'],
    note: string,
  ) => {
    try {
      await unwrap(
        api.POST('/api/v1/messages/{message_id}/feedback', {
          params: { path: { message_id: m.id } },
          body: { labels, note },
        }),
      )
      notify('Thanks — feedback saved for this reply.')
    } catch (e) {
      notify(errorText(e), 'error')
    }
  }

  const forkHere = async (m: Message | null, mode?: Schemas['Session']['mode']) => {
    if (!session) return
    try {
      const r = await withOperationKey(`fork:${sessionId}:${m?.id ?? 'all'}:${mode ?? ''}`, (key) =>
        unwrap(
          api.POST('/api/v1/sessions/{session_id}/forks', {
            params: { path: { session_id: sessionId }, header: { 'Idempotency-Key': key } },
            body: {
              expected_version: session.version,
              through_message_id: m?.id ?? null, // null = the whole conversation
              title: null,
              purpose: 'fork',
              ...(mode && mode !== session.mode ? { mode } : {}),
            },
          }),
        ),
      )
      await qc.invalidateQueries({ queryKey: ['history'] })
      navigate(`/rooms/${r.session.id}`)
    } catch (e) {
      notify(errorText(e), 'error')
    }
  }

  const branch = async (user: Message, purpose: 'edit' | 'regenerate', text?: string) => {
    if (!session) return
    const operationKey = `branch:${user.id}:${purpose}`
    const request = (message?: string) =>
      sendBranch({
        sourceId: sessionId,
        operationKey,
        forkBody: {
          expected_version: session.version,
          before_message_id: user.id,
          through_message_id: null,
          title: null,
          purpose,
        },
        message,
      })
    try {
      let id: string
      try {
        id = await request(text)
      } catch (e) {
        if (!(e instanceof PendingConflict)) throw e
        const choice = await resolvePending(e)
        if (!choice) return
        if (choice === 'discard') discardPending(operationKey)
        id = await request(choice === 'resend' ? e.earlier : text)
      }
      await qc.invalidateQueries({ queryKey: ['history'] })
      navigate(`/rooms/${id}`)
    } catch (e) {
      if (e instanceof TurnRejected) {
        notify(`The branch was created, but its turn was refused: ${e.message}`, 'error')
        navigate(`/rooms/${e.sessionId}`)
        return
      }
      notify(errorText(e), 'error')
    }
  }

  const regenerate = async (user: Message) => {
    const ok = await dialogs.confirm({
      title: 'Regenerate round',
      body: 'Creates a new branch just before this message and sends it again with the original settings and participants. This chat stays exactly as it is.',
      confirmLabel: 'Regenerate in a new branch',
    })
    if (ok) await branch(user, 'regenerate')
  }

  const editMessage = async (user: Message) => {
    const text = await dialogs.prompt({
      title: 'Edit message',
      label: 'Send as new branch — the original chat and its replies are kept',
      initial: user.text ?? '',
      confirmLabel: 'Send as new branch',
      maxLength: 16000,
      multiline: true,
    })
    if (text) await branch(user, 'edit', text)
  }

  return { setIntent, target, toggleSaved, sendFeedback, forkHere, regenerate, editMessage }
}

export type RoomActions = ReturnType<typeof useRoomActions>
