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

/**
 * An earlier send under this key ended without an answer (network), and the new request is
 * different. Neither may silently replace the other: the UI asks to resend or discard it.
 */
export class PendingConflict extends Error {
  draftKey: string
  earlier: string
  constructor(draftKey: string, earlier: string) {
    super('An earlier send may not have gone through.')
    this.draftKey = draftKey
    this.earlier = earlier
  }
}

export const discardPending = (draftKey: string) =>
  useDrafts.getState().set(draftKey, { pending: undefined })

const sameJson = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b)

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
  if (pending?.createKey && pending.createBody && !sameJson(pending.createBody, createBody))
    throw new PendingConflict(draftKey, pending.createBody.idea)
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
  draftKey: string = sessionId,
): Promise<Schemas['Run']> {
  const drafts = useDrafts.getState()
  let pending = drafts.get(draftKey)?.pending
  if (
    pending?.turnKey &&
    pending.turnBody &&
    !(pending.turnBody.message === body.message && sameJson(pending.turnBody.control, body.control))
  )
    throw new PendingConflict(draftKey, pending.turnBody.message)
  if (!pending?.turnKey || !pending.turnBody) {
    pending = { turnKey: newIdempotencyKey(), turnBody: body }
    drafts.set(draftKey, { pending })
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
    if (draftKey === sessionId) finishSend(sessionId, pending.turnBody!.message)
    else drafts.clear(draftKey)
    return run
  } catch (e) {
    forgetIfDefinitive(draftKey, e)
    throw e
  }
}

/**
 * Edit-and-branch / regenerate (doc 14): fork BEFORE the user message, then submit the returned
 * template (edited text for edit). Both requests keep stable keys under `operationKey` until the
 * turn is accepted, so a retry or refresh never creates a second branch or a second turn.
 */
export async function sendBranch(opts: {
  sourceId: string
  operationKey: string
  forkBody: Schemas['ForkCreate']
  message?: string
}): Promise<string> {
  const drafts = useDrafts.getState()
  let pending = drafts.get(opts.operationKey)?.pending
  if (pending?.turnBody && opts.message !== undefined && pending.turnBody.message !== opts.message)
    throw new PendingConflict(opts.operationKey, pending.turnBody.message)
  if (!pending?.forkKey || !pending.forkBody) {
    pending = {
      forkKey: newIdempotencyKey(),
      forkBody: opts.forkBody,
      turnKey: newIdempotencyKey(),
    }
    drafts.set(opts.operationKey, { text: opts.message ?? '', pending })
  }
  let result: Schemas['ForkResult']
  try {
    result = await unwrap(
      api.POST('/api/v1/sessions/{session_id}/forks', {
        params: {
          path: { session_id: opts.sourceId },
          header: { 'Idempotency-Key': pending.forkKey! },
        },
        body: pending.forkBody!,
      }),
    )
  } catch (e) {
    forgetIfDefinitive(opts.operationKey, e)
    throw e
  }
  const template = result.turn_template
  if (template && !pending.turnBody) {
    pending = {
      ...pending,
      sessionId: result.session.id,
      turnBody: { ...template, message: opts.message ?? template.message },
    }
    drafts.set(opts.operationKey, { pending })
  }
  if (pending.turnBody) {
    try {
      await unwrap(
        api.POST('/api/v1/sessions/{session_id}/turns', {
          params: {
            path: { session_id: result.session.id },
            header: { 'Idempotency-Key': pending.turnKey! },
          },
          body: pending.turnBody,
        }),
      )
    } catch (e) {
      if (e instanceof ApiError && e.status > 0) {
        // The branch exists; its turn was refused. Keep the text as that branch's draft.
        drafts.clear(opts.operationKey)
        useDrafts.getState().set(result.session.id, { text: pending.turnBody.message })
        throw new TurnRejected(result.session.id, e)
      }
      throw e
    }
  }
  drafts.clear(opts.operationKey)
  return result.session.id
}

/**
 * One stable idempotency key per user operation (`opKey`), kept until the server answers, so a
 * retry after a lost response returns the first result instead of creating a second chat/folder.
 */
export async function withOperationKey<T>(opKey: string, fn: (key: string) => Promise<T>) {
  const drafts = useDrafts.getState()
  let key = drafts.get(opKey)?.pending?.forkKey
  if (!key) {
    key = newIdempotencyKey()
    drafts.set(opKey, { pending: { forkKey: key } })
  }
  try {
    const out = await fn(key)
    useDrafts.getState().clear(opKey)
    return out
  } catch (e) {
    if (e instanceof ApiError && e.status > 0) useDrafts.getState().clear(opKey)
    throw e
  }
}
