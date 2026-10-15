import { expect, type Page, test } from '@playwright/test'
import { call, control, seedChat, waitIdle } from './helpers'

// Real-app screenshots for docs/screenshots (handoff/ui/README.md §State examples). Demo mode.
const OUT = '../docs/screenshots'
const IDEA = 'How could we make interview practice feel less intimidating?'

async function prefs(
  page: Page,
  theme: 'dark' | 'light',
  expanded: boolean,
  openFolders: string[] = [],
) {
  await page.addInitScript(
    ([t, e, f]) =>
      localStorage.setItem(
        'perspective-room:ui:v1',
        JSON.stringify({ state: { theme: t, sidebarExpanded: e, openFolderIds: f }, version: 1 }),
      ),
    [theme, expanded, openFolders] as const,
  )
}

async function turn(page: Page, id: string, message: string, over: Record<string, unknown> = {}) {
  const v = (await call(page, 'GET', `/api/v1/sessions/${id}`)).version
  await call(page, 'POST', `/api/v1/sessions/${id}/turns`, {
    expected_version: v,
    message,
    control: control(over),
  })
  await waitIdle(page, id)
}

async function shot(page: Page, name: string) {
  await page.waitForLoadState('networkidle')
  await page.waitForTimeout(400) // portraits and fonts settle
  await page.screenshot({ path: `${OUT}/${name}.png` })
}

test('capture the documented states', async ({ page, browser }) => {
  test.setTimeout(240_000)
  const folder = await call(page, 'POST', '/api/v1/folders', { name: 'Product ideas' })
  const room = await seedChat(page, 'Interview practice for students', {
    message: IDEA,
    folder_id: folder.id,
  })
  await seedChat(page, 'Team knowledge assistant', { folder_id: folder.id })
  await seedChat(page, 'A better team handover')
  await seedChat(page, 'Neighborhood tool sharing')

  for (const theme of ['dark', 'light'] as const) {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
    const p = await ctx.newPage()
    await prefs(p, theme, false)
    await p.goto(`/rooms/${room.id}`)
    await expect(p.getByTestId('contribution')).toHaveCount(3)
    await shot(p, `room-${theme}-rail`)
    await ctx.close()
    const ctx2 = await browser.newContext({ viewport: { width: 1440, height: 900 } })
    const p2 = await ctx2.newPage()
    await prefs(p2, theme, true, [folder.id])
    await p2.goto(`/rooms/${room.id}`)
    await expect(p2.getByRole('group', { name: 'Chats in Product ideas' })).toBeVisible()
    await shot(p2, `room-${theme}-sidebar-folder-open`)
    await ctx2.close()
  }

  // Search with results.
  await prefs(page, 'dark', true, [folder.id])
  await page.goto('/chats')
  await page.keyboard.press('ControlOrMeta+k')
  await page.getByRole('textbox', { name: 'Search chats' }).fill('team')
  await expect(page.getByRole('dialog').getByRole('link').first()).toBeVisible()
  await shot(page, 'search-results')
  await page.keyboard.press('Escape')

  // Folder view.
  await page.goto(`/folders/${folder.id}`)
  await expect(page.getByRole('main').getByRole('link', { name: /Team knowledge/ })).toBeVisible()
  await shot(page, 'folder-view')

  // Eight selected, eight replies (taller window so the whole panel shows).
  const eight = await seedChat(page, 'Community repair café')
  const v = (await call(page, 'GET', `/api/v1/sessions/${eight.id}`)).version
  await call(page, 'PATCH', `/api/v1/sessions/${eight.id}`, {
    expected_version: v,
    selected_persona_ids: [
      'mentor',
      'skeptic',
      'explorer',
      'strategist',
      'engineer',
      'customer',
      'civic',
      'health',
    ],
  })
  await turn(page, eight.id, 'Everyone: what would you try first?', { audience: 'panel' })
  await page.setViewportSize({ width: 1440, height: 1500 })
  await page.goto(`/rooms/${eight.id}`)
  await expect(page.getByTestId('contribution')).toHaveCount(3 + 8)
  await page.getByRole('region', { name: 'Turn', exact: true }).last().scrollIntoViewIfNeeded()
  await shot(page, 'eight-selected-eight-replies')
  await page.setViewportSize({ width: 1440, height: 900 })

  // A long reply with citations, expanded, with the Sources drawer open.
  await turn(page, eight.id, 'What does existing research say about repair events?', {
    research_override: 'force',
    audience: 'auto',
  })
  await page.goto(`/rooms/${eight.id}`)
  const last = page.getByRole('region', { name: 'Turn', exact: true }).last()
  await last.getByRole('button', { name: 'Read full response' }).click()
  await last.scrollIntoViewIfNeeded()
  await shot(page, 'long-cited-reply')
  await last
    .getByRole('button', { name: /^Source 1/ })
    .first()
    .click()
  await expect(page.getByRole('dialog', { name: 'Chat details' })).toBeVisible()
  await shot(page, 'sources-drawer')
  await page.keyboard.press('Escape')

  // A long multi-turn chat.
  for (const m of [
    'How would we find the first ten volunteers?',
    'What if the space is only free on Sundays?',
    'Summarize where we are.',
  ])
    await turn(page, eight.id, m, m.startsWith('Summarize') ? { audience: 'summary' } : {})
  await page.goto(`/rooms/${eight.id}`)
  await expect(page.getByTestId('summary')).toHaveCount(1)
  await shot(page, 'long-multi-turn-chat')

  // Mobile: navigation drawer and the room with its composer.
  const phone = await browser.newContext({
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
  })
  const m = await phone.newPage()
  await prefs(m, 'dark', false, [folder.id])
  await m.goto(`/rooms/${room.id}`)
  await expect(m.getByTestId('contribution')).toHaveCount(3)
  await shot(m, 'mobile-room-composer')
  await m.getByRole('button', { name: 'Open navigation' }).click()
  await expect(m.getByRole('dialog', { name: 'Navigation' })).toBeVisible()
  await shot(m, 'mobile-navigation')
  await phone.close()
})
