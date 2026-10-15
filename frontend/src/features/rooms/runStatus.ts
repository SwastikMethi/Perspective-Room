// What the end of a turn offers (doc 14 §Composer, Review Focus 1): Retry only when replies are
// missing and the failure can succeed on another try; a rejected key or unavailable model shows
// its sanitized message and points to Settings instead of a Retry that cannot work.
import type { Schemas } from '../../api/client'

const RETRYABLE = ['partial', 'failed', 'interrupted', 'cancelled']

export function retryOffer(run: Schemas['Run']): {
  retry: boolean
  error: string | null
  settings?: true
} {
  if (!RETRYABLE.includes(run.status)) return { retry: false, error: null }
  const missing = run.published_count < run.requested_count
  if (run.error && !run.error.retryable)
    return { retry: false, error: run.error.message, settings: true }
  return { retry: missing, error: run.error?.message ?? null }
}
