import { useNavigate } from 'react-router'
import { usePersonas } from '../../api/queries'
import { PersonaAvatar } from '../../components/PersonaAvatar'
import { PERSONA_UI, ROSTER } from '../../lib/personas'

/** The eight perspectives (doc 03 catalog): who they are, what they weigh, and a sample. */
export function PersonalitiesPage() {
  const personas = usePersonas()
  const navigate = useNavigate()
  const byId = new Map(personas.data?.items.map((p) => [p.id, p]))
  return (
    <section className="mx-auto max-w-[var(--layout-workspace-max)] px-4 py-8 sm:px-6 lg:px-12">
      <h1 className="text-[length:var(--text-title)] leading-tight font-semibold">Personalities</h1>
      <p className="mt-2 max-w-[68ch] text-muted">
        Eight fictional perspectives with different priorities. They are model-written roles, not
        real people or credentialed experts. Pick any of them for a chat, or ask one directly.
      </p>
      {personas.isPending && <p className="mt-6 text-muted">Loading…</p>}
      {personas.isError && (
        <p role="alert" className="mt-6">
          The catalog could not load: {personas.error.message}
        </p>
      )}
      <ul className="mt-6 grid gap-4 [grid-template-columns:repeat(auto-fill,minmax(min(100%,320px),1fr))]">
        {ROSTER.map((id) => {
          const p = byId.get(id)
          if (!p) return null
          return (
            <li key={id} className="flex flex-col rounded-card border border-border bg-surface p-5">
              <div className="flex items-center gap-3">
                <PersonaAvatar id={id} size={64} />
                <div className="min-w-0">
                  <h2 className="flex items-center gap-2 text-[19px] font-semibold">
                    <span
                      aria-hidden
                      className="size-2.5 rounded-full"
                      style={{ background: PERSONA_UI[id].accent }}
                    />
                    {PERSONA_UI[id].label}
                  </h2>
                  <p className="text-[14px] text-muted">{p.display_name}</p>
                </div>
              </div>
              <p className="mt-3">{p.tagline}</p>
              <h3 className="mt-3 text-[13px] font-medium text-muted">Cares about</h3>
              <ul className="mt-1 list-disc pl-5 text-[15px]">
                {p.priorities.map((x) => (
                  <li key={x}>{x}</li>
                ))}
              </ul>
              <h3 className="mt-3 text-[13px] font-medium text-muted">Example</h3>
              <p className="mt-1 text-[15px] italic [overflow-wrap:anywhere]">“{p.example}”</p>
              <button
                type="button"
                onClick={() => navigate(`/?ask=${id}`)}
                className="mt-4 inline-flex min-h-10 items-center self-start rounded-control bg-accent px-3 font-medium text-on-accent hover:bg-accent-hover"
              >
                Ask {PERSONA_UI[id].label} directly
              </button>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
