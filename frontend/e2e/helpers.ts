import { expect, type Page } from '@playwright/test'

export const control = (over: Record<string, unknown> = {}) => ({
  audience: 'auto',
  target_persona_id: null,
  move_override: null,
  reply_to_message_id: null,
  idea_card_ids: [],
  research_override: 'auto',
  ...over,
})

export async function call(page: Page, method: string, path: string, data?: unknown) {
  const r = await page.request.fetch(path, {
    method,
    data,
    headers: { 'Idempotency-Key': crypto.randomUUID() },
  })
  expect(r.ok(), `${method} ${path} → ${r.status()} ${await r.text()}`).toBeTruthy()
  return r.status() === 204 ? null : r.json()
}

export async function waitIdle(page: Page, sessionId: string) {
  await expect
    .poll(async () => (await call(page, 'GET', `/api/v1/sessions/${sessionId}`)).active_run_id, {
      timeout: 20_000,
    })
    .toBeNull()
}

/** A chat with one completed turn, created through the API (the UI flows are tested elsewhere). */
export async function seedChat(
  page: Page,
  idea: string,
  opts: { message?: string; folder_id?: string; turn?: Record<string, unknown> } = {},
) {
  const s = await call(page, 'POST', '/api/v1/sessions', {
    idea,
    ...(opts.folder_id ? { folder_id: opts.folder_id } : {}),
  })
  await call(page, 'POST', `/api/v1/sessions/${s.id}/turns`, {
    expected_version: s.version,
    message: opts.message ?? idea,
    control: control(opts.turn),
  })
  await waitIdle(page, s.id)
  return s as { id: string; title: string }
}

export async function expandedSidebar(page: Page) {
  await page.addInitScript(() => {
    if (!localStorage.getItem('perspective-room:ui:v1'))
      localStorage.setItem(
        'perspective-room:ui:v1',
        JSON.stringify({
          state: { theme: 'dark', sidebarExpanded: true, openFolderIds: [] },
          version: 1,
        }),
      )
  })
}

export const unique = (word: string) => `${word}${Math.random().toString(36).slice(2, 8)}`
