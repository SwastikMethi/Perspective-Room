import { expect, test } from '@playwright/test'
import { call, control, expandedSidebar, seedChat, unique, waitIdle } from './helpers'

const ROSTER = [
  'mentor',
  'skeptic',
  'explorer',
  'strategist',
  'engineer',
  'customer',
  'civic',
  'health',
]

test('select all eight and ask everyone: eight cards in roster order, no page overflow (T30)', async ({
  page,
}) => {
  const s = await seedChat(page, unique('Eight voices '))
  await page.goto(`/rooms/${s.id}`)
  await page.getByRole('button', { name: 'Select all' }).click()
  await expect(page.getByText('8 selected · 8 available')).toBeVisible()
  await page.getByRole('combobox', { name: 'Who answers' }).selectOption('panel')
  await page.getByLabel('Message', { exact: true }).fill('Everyone, what is the first test?')
  await page.getByRole('button', { name: 'Send', exact: true }).click()
  const lastGroup = page.getByRole('region', { name: 'Turn', exact: true }).last()
  await expect(lastGroup.getByTestId('contribution')).toHaveCount(8, { timeout: 20_000 })
  const order = await lastGroup
    .getByTestId('contribution')
    .evaluateAll((els) => els.map((e) => e.getAttribute('data-persona')))
  expect(order).toEqual(ROSTER)
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
  expect(overflow).toBeLessThanOrEqual(0)
})

test('Ask more targets that persona; saving an idea shows in Saved ideas', async ({ page }) => {
  const s = await seedChat(page, unique('Ask more '))
  await page.goto(`/rooms/${s.id}`)
  const skeptic = page.locator('[data-testid="contribution"][data-persona="skeptic"]').first()
  await skeptic.hover()
  await skeptic.getByRole('button', { name: 'Ask more' }).click()
  await expect(page.getByText('To Skeptic', { exact: true })).toBeVisible()
  await page.getByLabel('Message', { exact: true }).fill('Say more about the test')
  await page.getByRole('button', { name: 'Send', exact: true }).click()
  const lastGroup = page.getByRole('region', { name: 'Turn', exact: true }).last()
  await expect(lastGroup.getByTestId('contribution')).toHaveCount(1, { timeout: 15_000 })
  await expect(lastGroup.getByTestId('contribution')).toHaveAttribute('data-persona', 'skeptic')

  await skeptic.getByRole('button', { name: /^Save idea/ }).click()
  await expect(page.getByRole('button', { name: /Saved ideas/ })).toContainText('(1)')
  await page.getByRole('button', { name: /Saved ideas/ }).click()
  await expect(
    page.getByRole('dialog', { name: 'Chat details' }).getByRole('listitem'),
  ).toHaveCount(1)
})

test('editing the first message branches before it and keeps the original chat (T32)', async ({
  page,
}) => {
  const s = await seedChat(page, unique('Original idea '), { message: 'Original opening' })
  await page.goto(`/rooms/${s.id}`)
  const first = page.getByTestId('user-message').first()
  await first.hover()
  await first.getByRole('button', { name: 'More actions for your message' }).click()
  await page.getByRole('menuitem', { name: /Edit message/ }).click()
  const field = page.getByRole('dialog').getByRole('textbox')
  await field.fill('Edited opening')
  await page.getByRole('button', { name: 'Send as new branch' }).click()
  await expect(page).not.toHaveURL(new RegExp(s.id))
  await expect(page.getByTestId('user-message').first()).toContainText('Edited opening')
  await expect(page.getByTestId('contribution')).toHaveCount(3, { timeout: 15_000 })
  const original = await call(page, 'GET', `/api/v1/sessions/${s.id}/messages`)
  expect(original.items[0].text).toBe('Original opening')
})

test('regenerate a completed round in a new branch with the same text (T33)', async ({ page }) => {
  const s = await seedChat(page, unique('Regenerate '), { message: 'Round to regenerate' })
  await page.goto(`/rooms/${s.id}`)
  const card = page.getByTestId('contribution').first()
  await card.hover()
  await card.getByRole('button', { name: /^More actions for/ }).click()
  await page.getByRole('menuitem', { name: /Regenerate round/ }).click()
  await page.getByRole('button', { name: 'Regenerate in a new branch' }).click()
  await expect(page).not.toHaveURL(new RegExp(s.id))
  await expect(page.getByTestId('user-message').first()).toContainText('Round to regenerate')
  await expect(page.getByTestId('contribution')).toHaveCount(3, { timeout: 15_000 })
})

test('a partial round offers Retry missing replies, which fills only the gap (T34)', async ({
  page,
}) => {
  const s = await seedChat(page, unique('Partial '), {
    message: '[[demo:fail_once=skeptic]] Panel with one failure',
    turn: { audience: 'panel' },
  })
  await page.goto(`/rooms/${s.id}`)
  await expect(page.getByTestId('contribution')).toHaveCount(2)
  await page.getByRole('button', { name: 'Retry missing replies' }).click()
  await waitIdle(page, s.id)
  await expect(page.getByTestId('contribution')).toHaveCount(3, { timeout: 15_000 })
  await expect(page.getByRole('button', { name: 'Retry missing replies' })).toHaveCount(0)
})

test('switching chats in-app starts each room fresh at its latest turn', async ({ page }) => {
  await expandedSidebar(page)
  const a = await seedChat(page, unique('Two turns '), { message: 'First turn of A' })
  const v = (await call(page, 'GET', `/api/v1/sessions/${a.id}`)).version
  await call(page, 'POST', `/api/v1/sessions/${a.id}/turns`, {
    expected_version: v,
    message: 'Second turn of A',
    control: control(),
  })
  await waitIdle(page, a.id)
  const titleA = (await call(page, 'GET', `/api/v1/sessions/${a.id}`)).title
  const b = await seedChat(page, unique('Other chat '))
  await page.goto(`/rooms/${b.id}`)
  await page.getByLabel('Message', { exact: true }).fill('draft in B')
  await page
    .getByRole('navigation', { name: 'Primary' })
    .getByRole('link', { name: titleA })
    .click()
  await expect(page).toHaveURL(new RegExp(a.id))
  const last = page.getByTestId('user-message').last()
  await expect(last).toContainText('Second turn of A')
  await expect(last).toBeInViewport()
  await expect(page.getByRole('button', { name: 'New responses' })).toHaveCount(0)
  await expect(page.getByLabel('Message', { exact: true })).toHaveValue('')
})
