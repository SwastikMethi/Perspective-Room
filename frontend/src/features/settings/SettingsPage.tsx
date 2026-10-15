import { useMutation } from '@tanstack/react-query'
import { api, type Schemas, unwrap } from '../../api/client'
import { useSettings } from '../../api/queries'
import { dialogs } from '../../components/Dialogs'
import { ThemeSwitch } from '../../components/ThemeSwitch'
import { DRAFTS_STORAGE_KEY } from '../../stores/drafts'
import { safeStorage } from '../../stores/safeStorage'
import { UI_STORAGE_KEY } from '../../stores/ui'

const STATUS_TEXT: Record<string, string> = {
  ok: 'Connected',
  missing: 'Not configured',
  failed: 'Check failed',
  demo: 'Demo mode',
}
const card = 'rounded-card border border-border bg-surface p-5'

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex flex-wrap justify-between gap-2 border-b border-border py-2 last:border-0">
      <dt className="text-muted">{label}</dt>
      <dd className="font-medium [overflow-wrap:anywhere]">{value}</dd>
    </div>
  )
}

export function SettingsPage() {
  const settings = useSettings()
  const check = useMutation({
    mutationFn: () => unwrap(api.POST('/api/v1/provider-checks')),
  })
  const s = settings.data
  const limits = (s?.limits ?? {}) as Record<string, number | boolean | null>
  const result: Schemas['ProviderCheck'] | undefined = check.data
  return (
    <section className="mx-auto max-w-[var(--layout-workspace-max)] px-4 py-8 sm:px-6 lg:px-12">
      <h1 className="text-[length:var(--text-title)] leading-tight font-semibold">Settings</h1>
      <p className="mt-2 text-muted">
        Everything here runs on this computer. Keys stay in the server’s .env file and are never
        shown.
      </p>
      {settings.isError && (
        <p role="alert" className="mt-4">
          Settings could not load: {settings.error.message}
        </p>
      )}
      {s && (
        <div className="mt-6 grid gap-4 lg:grid-cols-2">
          <section className={card} aria-labelledby="set-providers">
            <h2 id="set-providers" className="text-[19px] font-semibold">
              Providers
            </h2>
            <dl className="mt-2">
              <Row
                label="Mode"
                value={
                  s.provider_mode === 'demo'
                    ? 'Demo — deterministic fixtures, no external calls'
                    : 'Live'
                }
              />
              <Row
                label="OpenAI (generation and research)"
                value={s.openai_configured ? 'Key configured' : 'Key missing'}
              />
              <Row
                label="Jev (coordination)"
                value={s.jev_configured ? 'Key configured' : 'Key missing'}
              />
              <Row label="Generation model" value={s.openai_model} />
              <Row label="Research model" value={s.research_model} />
              <Row label="Jev model" value={s.jev_model} />
            </dl>
            <button
              type="button"
              onClick={() => check.mutate()}
              disabled={check.isPending}
              className="mt-4 inline-flex min-h-10 items-center rounded-control bg-accent px-4 font-medium text-on-accent hover:bg-accent-hover disabled:opacity-60"
            >
              {check.isPending ? 'Checking…' : 'Check connection'}
            </button>
            <p className="mt-1 text-[13px] text-muted">
              Lists models only — no text is generated and nothing is billed for generation.
            </p>
            {check.isError && (
              <p role="alert" className="mt-2">
                The check could not run: {check.error.message}
              </p>
            )}
            {result && (
              <ul className="mt-3 space-y-1 text-[15px]" aria-live="polite">
                {(['openai', 'jev'] as const).map((k) => (
                  <li key={k}>
                    <strong>{k === 'openai' ? 'OpenAI' : 'Jev'}:</strong>{' '}
                    {result[k].status === 'demo'
                      ? result[k].message
                      : `${STATUS_TEXT[result[k].status]} — ${result[k].message}`}
                  </li>
                ))}
              </ul>
            )}
            {s.provider_mode === 'live' && (!s.openai_configured || !s.jev_configured) && (
              <p className="mt-3 text-[14px] text-muted">
                Add missing keys to <code>.env</code> and restart. For an offline walkthrough, set{' '}
                <code>APP_PROVIDER_MODE=demo</code> — demo replies are labeled and never mixed with
                live ones.
              </p>
            )}
          </section>
          <section className={card} aria-labelledby="set-limits">
            <h2 id="set-limits" className="text-[19px] font-semibold">
              Limits
            </h2>
            <dl className="mt-2">
              <Row label="Replies per automatic turn" value={limits.auto_contributions} />
              <Row label="Replies in a full panel" value={limits.panel_contributions} />
              <Row label="Research jobs per turn" value={limits.research_jobs_per_turn} />
              <Row label="Revisions per turn" value={limits.repairs_per_turn} />
              <Row
                label="Longest message"
                value={`${limits.user_message_chars ?? '?'} characters`}
              />
              <Row label="Chats running at once" value={limits.concurrent_session_runs} />
            </dl>
            <h3 className="mt-4 font-semibold">Cost</h3>
            <p className="mt-1 text-[15px] text-muted">
              Cost estimates show as unknown: no price table is configured, so the app does not
              guess.
              {limits.max_session_usd != null
                ? ` A per-chat cap of $${limits.max_session_usd} is set, but it cannot be enforced without prices — runs show a note instead.`
                : ' No spending cap is set.'}
            </p>
          </section>
          <section className={card} aria-labelledby="set-appearance">
            <h2 id="set-appearance" className="text-[19px] font-semibold">
              Appearance
            </h2>
            <p className="mt-1 text-[15px] text-muted">Saved in this browser only.</p>
            <div className="mt-3">
              <ThemeSwitch />
            </div>
          </section>
          <section className={card} aria-labelledby="set-data">
            <h2 id="set-data" className="text-[19px] font-semibold">
              Local data
            </h2>
            <p className="mt-1 text-[15px] text-muted">
              Chats, folders, sources and ratings live in the local PostgreSQL database. Back up and
              restore from a terminal in the project folder:
            </p>
            <pre className="mt-2 overflow-x-auto rounded-control border border-border bg-canvas p-3 text-[13px]">
              {`scripts/db_backup.sh
scripts/db_restore.sh backups/<file>.dump
docker compose exec app python -m app.cli delete-eval <batch-id>`}
            </pre>
            <p className="mt-3 text-[15px] text-muted">
              This browser also keeps your theme, sidebar state and unsent drafts. They are not part
              of a backup.
            </p>
            <button
              type="button"
              className="mt-3 inline-flex min-h-10 items-center rounded-control border border-danger px-4 font-medium text-danger hover:bg-surface-subtle"
              onClick={async () => {
                const ok = await dialogs.confirm({
                  title: 'Clear this browser’s workspace state?',
                  body: 'Removes unsent drafts, theme and sidebar preferences from this browser. Chats in the database are not affected.',
                  confirmLabel: 'Clear browser state',
                  danger: true,
                })
                if (!ok) return
                for (const k of [UI_STORAGE_KEY, DRAFTS_STORAGE_KEY, 'perspective-room:lab:v1'])
                  safeStorage.removeItem(k) // never throws, even when storage is blocked
                window.location.assign('/')
              }}
            >
              Clear local workspace state
            </button>
          </section>
        </div>
      )}
    </section>
  )
}
