import type { Schemas } from '../../api/client'
import { retryOffer } from './runStatus'

const run = (over: Partial<Schemas['Run']>): Schemas['Run'] =>
  ({
    id: 'r',
    session_id: 's',
    status: 'partial',
    stage: 'finished',
    published_count: 2,
    requested_count: 3,
    degraded: false,
    warning_codes: [],
    error: null,
    usage: {
      input_tokens: null,
      output_tokens: null,
      estimated_cost_usd: null,
      usage_incomplete: false,
    },
    session_version: 2,
    created_at: '',
    updated_at: '',
    ...over,
  }) as Schemas['Run']

const err = (code: string, retryable: boolean) => ({
  code,
  message: `msg ${code}`,
  retryable,
  request_id: '',
  details: {},
})

test('a partial round with missing replies offers Retry', () => {
  expect(retryOffer(run({}))).toEqual({ retry: true, error: null })
})

test('a rejected key never offers Retry and surfaces the sanitized message', () => {
  const r = retryOffer(
    run({ status: 'failed', published_count: 0, error: err('provider_not_ready', false) }),
  )
  expect(r).toEqual({ retry: false, error: 'msg provider_not_ready', settings: true })
})

test('a stopped round that already published everything offers nothing', () => {
  expect(retryOffer(run({ status: 'cancelled', published_count: 3, requested_count: 3 }))).toEqual({
    retry: false,
    error: null,
  })
})

test('a retryable failure keeps Retry and shows why it failed', () => {
  const r = retryOffer(
    run({ status: 'failed', published_count: 0, error: err('provider_error', true) }),
  )
  expect(r).toEqual({ retry: true, error: 'msg provider_error' })
})

test('completed and running rounds offer nothing', () => {
  expect(retryOffer(run({ status: 'completed', published_count: 3 }))).toEqual({
    retry: false,
    error: null,
  })
  expect(retryOffer(run({ status: 'running' }))).toEqual({ retry: false, error: null })
})
