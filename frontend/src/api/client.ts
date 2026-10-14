// Typed REST client generated from handoff/contracts/openapi.yaml (src/api/schema.d.ts).
import createClient from 'openapi-fetch'
import type { components, paths } from './schema'

export type Schemas = components['schemas']
export type ApiErrorBody = Schemas['Error']

export class ApiError extends Error {
  status: number
  error: ApiErrorBody

  constructor(status: number, error: ApiErrorBody) {
    super(error.message)
    this.status = status
    this.error = error
  }

  get code() {
    return this.error.code
  }
}

export const api = createClient<paths>({ baseUrl: '' })

export function newIdempotencyKey(): string {
  return crypto.randomUUID()
}

function isErrorBody(v: unknown): v is ApiErrorBody {
  return typeof v === 'object' && v !== null && 'code' in v && 'message' in v
}

/** Resolve an openapi-fetch call to its data, or throw an ApiError (network failures included). */
export async function unwrap<T>(
  call: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  let result: { data?: T; error?: unknown; response: Response }
  try {
    result = await call
  } catch {
    throw new ApiError(0, {
      code: 'network_error',
      message: 'The app server could not be reached.',
      retryable: true,
      request_id: '',
      details: {},
    })
  }
  const { data, error, response } = result
  if (!response.ok || error !== undefined) {
    throw new ApiError(
      response.status,
      isErrorBody(error)
        ? error
        : {
            code: 'http_error',
            message: `Request failed (${response.status}).`,
            retryable: response.status >= 500,
            request_id: response.headers.get('x-request-id') ?? '',
            details: {},
          },
    )
  }
  return data as T
}
