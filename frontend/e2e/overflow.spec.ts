import { expect, type Page, test } from '@playwright/test'
import { call, control, seedChat, unique, waitIdle } from './helpers'

// Review Focus 5: unbroken 2,000-character lines and a 16,000-character message never cause
// page-level horizontal overflow; long user text collapses with an expand control.

async function noHorizontalOverflow(page: Page) {
  const widths = await page.evaluate(() => {
    const main = document.getElementById('main')!
    return {
      doc: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      main: main.scrollWidth - main.clientWidth,
    }
  })
  expect(widths.doc).toBeLessThanOrEqual(0)
  expect(widths.main).toBeLessThanOrEqual(0)
}

test('long, unbroken and eight-wide content stays inside the page', async ({ page }) => {
  const url = 'https://example.org/' + 'a'.repeat(2000)
  const code = '`' + 'x'.repeat(2000) + '`'
  const s = await seedChat(page, unique('Overflow '), {
    message: `Check this link ${url} and ${code}`,
  })
  const long = 'A sentence that keeps going for a while. '.repeat(400).slice(0, 16_000)
  let v = (await call(page, 'GET', `/api/v1/sessions/${s.id}`)).version
  await call(page, 'POST', `/api/v1/sessions/${s.id}/turns`, {
    expected_version: v,
    message: long,
    control: control(),
  })
  await waitIdle(page, s.id)
  v = (await call(page, 'GET', `/api/v1/sessions/${s.id}`)).version
  await call(page, 'PATCH', `/api/v1/sessions/${s.id}`, {
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
  v = (await call(page, 'GET', `/api/v1/sessions/${s.id}`)).version
  await call(page, 'POST', `/api/v1/sessions/${s.id}/turns`, {
    expected_version: v,
    message: '[[demo:long]] Everyone, in depth please.',
    control: control({ audience: 'panel' }),
  })
  await waitIdle(page, s.id)

  await page.goto(`/rooms/${s.id}`)
  await expect(page.getByTestId('contribution')).toHaveCount(3 + 3 + 8)
  await noHorizontalOverflow(page)

  const longMsg = page
    .getByTestId('user-message')
    .filter({ hasText: 'A sentence that keeps going' })
  const expand = longMsg.getByRole('button', { name: 'Show full message' })
  await expect(expand).toBeVisible()
  await expand.click()
  await expect(longMsg.getByRole('button', { name: 'Show less' })).toBeVisible()
  await noHorizontalOverflow(page)

  const group = page.getByRole('region', { name: 'Turn', exact: true }).last()
  await group.getByRole('button', { name: 'Read full response' }).click()
  await noHorizontalOverflow(page)
  const width = page.viewportSize()!.width
  const columns = Number(await group.locator('[data-columns]').getAttribute('data-columns'))
  expect(columns).toBe(1) // expanded replies span the group
  await group.getByRole('button', { name: 'Show compact cards' }).click()
  const compact = Number(await group.locator('[data-columns]').getAttribute('data-columns'))
  expect(compact).toBeLessThanOrEqual(width < 640 ? 1 : width < 1100 ? 2 : 3)
})
