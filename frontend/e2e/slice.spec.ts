import { expect, test } from '@playwright/test'

test('new chat → contributions → refresh shows the same transcript once', async ({ page }) => {
  await page.goto('/')
  await page.getByLabel('Your idea').fill('A neighborhood tool-sharing service for renters')
  await page.getByLabel('Your idea').press('Enter')
  await expect(page).toHaveURL(/\/rooms\//)
  const cards = page.getByTestId('contribution')
  await expect(cards).toHaveCount(3)
  await expect(page.getByTestId('user-message')).toHaveCount(1)
  await page.reload()
  await expect(cards).toHaveCount(3)
  await expect(page.getByTestId('user-message')).toHaveCount(1)
})

test('Stop a delayed run: no late replies arrive', async ({ page }) => {
  await page.goto('/')
  await page.getByLabel('Your idea').fill('[[demo:delay=1500]] A slow idea to stop')
  await page.getByRole('button', { name: 'Send', exact: true }).click()
  await expect(page).toHaveURL(/\/rooms\//)
  await expect(page.getByTestId('contribution')).toHaveCount(1, { timeout: 15_000 })
  await page.getByRole('button', { name: 'Stop' }).click()
  await expect(page.getByRole('button', { name: 'Send', exact: true })).toBeVisible({
    timeout: 10_000,
  })
  const count = await page.getByTestId('contribution').count()
  await page.waitForTimeout(3500)
  await expect(page.getByTestId('contribution')).toHaveCount(count)
  expect(count).toBeLessThan(3)
})

test('double Enter on the composer sends one turn', async ({ page }) => {
  await page.goto('/')
  const box = page.getByLabel('Your idea')
  await box.fill('Quick double send check')
  await box.press('Enter')
  await box.press('Enter').catch(() => {})
  await expect(page).toHaveURL(/\/rooms\//)
  await expect(page.getByTestId('contribution')).toHaveCount(3)
  await expect(page.getByTestId('user-message')).toHaveCount(1)
})

test('reload mid-run reconnects and shows every reply exactly once', async ({ page }) => {
  await page.goto('/')
  await page.getByLabel('Your idea').fill('[[demo:delay=1200]] Reconnect after a reload')
  await page.getByLabel('Your idea').press('Enter')
  await expect(page).toHaveURL(/\/rooms\//)
  await expect(page.getByTestId('contribution')).toHaveCount(1, { timeout: 15_000 })
  await page.reload()
  await expect(page.getByTestId('contribution')).toHaveCount(3, { timeout: 15_000 })
  for (const persona of ['mentor', 'skeptic', 'explorer'])
    await expect(
      page.locator(`[data-testid="contribution"][data-persona="${persona}"]`),
    ).toHaveCount(1)
  await expect(page.getByRole('button', { name: 'Send', exact: true })).toBeVisible()
})
