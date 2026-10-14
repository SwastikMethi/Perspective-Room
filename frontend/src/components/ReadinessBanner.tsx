import { Link } from 'react-router'
import { useSettings } from '../api/queries'

const bar = 'border-b border-border bg-surface-subtle px-6 py-2 text-sm'

/** Honest provider state: demo label, unreachable server, or every missing live key by name. */
export function ReadinessBanner() {
  const { data, isError } = useSettings()
  if (isError) {
    return (
      <div role="alert" className={bar}>
        <strong>The app server cannot be reached.</strong> Check that <code>docker compose up</code>{' '}
        is running; unsent text stays in the composer.
      </div>
    )
  }
  if (!data) return null
  if (data.provider_mode === 'demo') {
    return (
      <p role="status" className={bar + ' py-1.5 text-[13px]'}>
        <strong>Demo mode</strong> — deterministic fixtures, no external calls. Replies are not real
        model output.
      </p>
    )
  }
  const missing = [
    !data.openai_configured && 'OPENAI_API_KEY',
    !data.jev_configured && 'TYPESAFE_API_KEY',
  ].filter(Boolean) as string[]
  if (missing.length === 0) return null
  return (
    <div role={data.openai_configured ? 'status' : 'alert'} className={bar}>
      <strong>Missing {missing.join(' and ')}.</strong>{' '}
      {data.openai_configured
        ? 'Jev-guided turns use the labeled fixed-order fallback until Jev is configured. '
        : 'Live conversations cannot start. '}
      Set {missing.length > 1 ? 'them' : 'it'} in <code>.env</code> and restart, or set{' '}
      <code>APP_PROVIDER_MODE=demo</code> for a labeled offline demo.{' '}
      <Link to="/settings" className="underline">
        Settings
      </Link>
    </div>
  )
}
