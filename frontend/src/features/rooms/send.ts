// Sending turns. The first Send of a new chat creates the session and its opening turn with two
// distinct, persisted idempotency keys; a refresh resends the stored bodies, never new ones.
import { ApiError, api, newIdempotencyKey, type Schemas, unwrap } from '../../api/client'
import { useDrafts } from '../../stores/drafts'

export function defaultControl(): Schemas['TurnControl'] {
  return {
    audience: 'auto',
    target_persona_id: null,
    move_override: null,
    reply_to_message_id: null,
    idea_card_ids: [],
    research_override: 'auto',
  }
}

/** A definitive server answer means the request did not go through; drop the keys. */
function forgetIfDefinitive(draftKey: string, e: unknown) {
  if (e instanceof ApiError && e.status > 0)
    useDrafts.getState().set(draftKey, { pending: undefined })
}

export async function sendNewChat(
  draftKey: string,
  createBody: Schemas['SessionCreate'],
  control: Schemas['TurnControl'] = defaultControl(),
): Promise<string> {
  const drafts = useDrafts.getState()
  let pending = drafts.get(draftKey)?.pending
  if (!pending?.createKey || !pending.createBody) {
    pending = { createKey: newIdempotencyKey(), createBody, turnKey: newIdempotencyKey() }
    drafts.set(draftKey, { text: createBody.idea, pending })
  }
  try {
    const session = await unwrap(
      api.POST('/api/v1/sessions', {
        body: pending.createBody!,
        params: { header: { 'Idempotency-Key': pending.createKey! } },
      }),
    )
    if (!pending.turnBody) {
      pending = {
        ...pending,
        sessionId: session.id,
        turnBody: { expected_version: session.version, message: pending.createBody!.idea, control },
      }
      drafts.set(draftKey, { pending })
    }
    await unwrap(
      api.POST('/api/v1/sessions/{session_id}/turns', {
        params: {
          path: { session_id: session.id },
          header: { 'Idempotency-Key': pending.turnKey! },
        },
        body: pending.turnBody!,
      }),
    )
    finishSend(draftKey, pending.createBody!.idea)
    return session.id
  } catch (e) {
    if (!pending.sessionId) forgetIfDefinitive(draftKey, e)
    else if (e instanceof ApiError && e.status > 0) throw new TurnRejected(pending.sessionId, e)
    throw e
  }
}

/** The chat exists but its opening turn was refused: the UI moves the text into that room. */
export class TurnRejected extends Error {
  sessionId: string
  cause: ApiError
  constructor(sessionId: string, cause: ApiError) {
    super(cause.error.message)
    this.sessionId = sessionId
    this.cause = cause
  }
}

/** Clear the pending send; clear the text only if the user did not change it meanwhile. */
function finishSend(draftKey: string, sent: string) {
  const drafts = useDrafts.getState()
  const current = drafts.get(draftKey)
  if (!current || current.text.trim() === sent.trim()) drafts.clear(draftKey)
  else drafts.set(draftKey, { pending: undefined })
}

export async function sendTurn(
  sessionId: string,
  body: Schemas['TurnCreate'],
): Promise<Schemas['Run']> {
  const drafts = useDrafts.getState()
  let pending = drafts.get(sessionId)?.pending
  if (!pending?.turnKey || !pending.turnBody) {
    pending = { turnKey: newIdempotencyKey(), turnBody: body }
    drafts.set(sessionId, { pending })
  }
  try {
    const run = await unwrap(
      api.POST('/api/v1/sessions/{session_id}/turns', {
        params: {
          path: { session_id: sessionId },
          header: { 'Idempotency-Key': pending.turnKey! },
        },
        body: pending.turnBody!,
      }),
    )
    finishSend(sessionId, pending.turnBody!.message)
    return run
  } catch (e) {
    forgetIfDefinitive(sessionId, e)
    throw e
  }
}
