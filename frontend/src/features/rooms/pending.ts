// What to do when an earlier send ended without an answer and the user now sends something else.
import { dialogs } from '../../components/Dialogs'
import type { PendingConflict } from './send'

export async function resolvePending(e: PendingConflict): Promise<'resend' | 'discard' | null> {
  const earlier = e.earlier.length > 80 ? `${e.earlier.slice(0, 80)}…` : e.earlier
  const choice = await dialogs.choose({
    title: 'An earlier send may not have gone through',
    body: `The connection dropped while sending “${earlier}”, so it may or may not have reached the app.`,
    options: [
      { value: 'resend', label: 'Check and resend the earlier message (never duplicated)' },
      { value: 'discard', label: 'Discard it and send what is in the box now' },
    ],
    initial: 'resend',
    confirmLabel: 'Continue',
  })
  return choice === 'resend' || choice === 'discard' ? choice : null
}
