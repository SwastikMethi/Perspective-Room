import { expect, test } from '@playwright/test'
import { seedChat, unique } from './helpers'

// doc 10 failure walkthrough via demo directives: honest notes, kept replies, no resubmits.

async function send(page: import('@playwright/test').Page, text: string) {
  await page.getByLabel('Message', { exact: true }).fill(text)
  await page.getByRole('button', { name: 'Send', exact: true }).click()
}

test('a provider failure keeps earlier replies, says so, and offers a retry', async ({ page }) => {
  const s = await seedChat(page, unique('Provider failure '))
  await page.goto(`/rooms/${s.id}`)
  await expect(page.getByTestId('contribution')).toHaveCount(3)
  await send(page, '[[demo:fail=all]] Another angle please')
  await expect(page.getByText('Some replies could not be produced.')).toBeVisible({
    timeout: 20_000,
  })
  await expect(page.getByTestId('contribution')).toHaveCount(3)
  await expect(page.getByRole('button', { name: 'Retry missing replies' })).toBeVisible()
})

test('a failed search is disclosed and the room keeps brainstorming', async ({ page }) => {
  const s = await seedChat(page, unique('Research failure '))
  await page.goto(`/rooms/${s.id}`)
  await page.getByRole('combobox', { name: 'Research' }).selectOption('force')
  await send(page, '[[demo:research=fail]] What do studies say?')
  await expect(
    page.getByText('Current facts were not checked; replies use labeled assumptions.'),
  ).toBeVisible({
    timeout: 20_000,
  })
  await expect(page.getByTestId('contribution')).toHaveCount(6)
})

test('a Jev outage uses the labeled fixed order', async ({ page }) => {
  const s = await seedChat(page, unique('Jev down '))
  await page.goto(`/rooms/${s.id}`)
  await send(page, '[[demo:jev=down]] Keep going')
  await expect(
    page.getByText(/Fixed order used for this turn\.|fixed order used for this turn/),
  ).toBeVisible({
    timeout: 20_000,
  })
})

test('a dropped event stream reconnects without resubmitting the turn', async ({ page }) => {
  const s = await seedChat(page, unique('Disconnect '))
  const turnPosts: string[] = []
  page.on('request', (r) => {
    if (r.method() === 'POST' && r.url().endsWith('/turns')) turnPosts.push(r.url())
  })
  await page.goto(`/rooms/${s.id}`)
  let blocked = true
  await page.route('**/api/v1/runs/*/events*', (route) =>
    blocked ? route.abort('connectionreset') : route.continue(),
  )
  await send(page, '[[demo:delay=600]] A slower turn')
  await page.waitForTimeout(800)
  blocked = false
  await expect(page.getByTestId('contribution')).toHaveCount(6, { timeout: 30_000 })
  await page.waitForTimeout(1500)
  await expect(page.getByTestId('contribution')).toHaveCount(6) // each reply exactly once
  expect(turnPosts).toHaveLength(1)
})
