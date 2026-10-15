import { expect, test } from '@playwright/test'

test('a small blinded batch runs, is rated, revealed, and reports honest results', async ({
  page,
}) => {
  await page.goto('/lab')
  await page.getByRole('checkbox', { name: /case_01 ·/ }).check()
  await page.getByRole('checkbox', { name: /Fixed panel \(B\)/ }).uncheck()
  await expect(page.getByText('2 trials planned (limit 90)')).toBeVisible()
  await page.getByRole('button', { name: 'Run batch' }).click()
  await expect(
    page.getByRole('heading', { name: /Batch .* · (completed|running|queued)/ }),
  ).toBeVisible()
  await expect(page.getByRole('heading', { name: /· completed/ })).toBeVisible({ timeout: 45_000 })

  // Blind: neutral labels, no condition names on the outputs.
  const outputs = page.getByRole('article')
  await expect(outputs).toHaveCount(2)
  await expect(page.getByRole('heading', { name: 'Output 1' })).toBeVisible()
  await expect(outputs.filter({ hasText: /Jev-guided|Standard ·/ })).toHaveCount(0)

  await page.getByLabel('Rater alias').fill('rater-a')
  const first = outputs.first()
  for (const legend of ['Useful breadth', 'Usefulness', 'Redundancy (lower is better)'])
    await first.getByRole('group', { name: legend }).getByText('4', { exact: true }).click()
  await first.getByRole('button', { name: /Save rating for Output/ }).click()
  await expect(first.getByText(/rated ×1/)).toBeVisible()

  await page.getByRole('button', { name: 'Reveal conditions' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Reveal conditions' }).click()
  await expect(outputs.filter({ hasText: /Jev-guided|Standard/ })).toHaveCount(2)

  await page.getByRole('tab', { name: 'Results' }).click()
  await page.getByRole('button', { name: 'Reveal and show results' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Reveal and show results' }).click()
  const notes = page.getByRole('list', { name: 'Before comparing' })
  await expect(notes.getByRole('listitem').first()).toContainText('Planned 2 trials')
  await expect(notes).toContainText('Demo provider')
  await expect(page.getByRole('table', { name: 'Conditions' })).toBeVisible()
})

test('an oversized request is blocked before anything is created', async ({ page }) => {
  await page.goto('/lab')
  await page.getByRole('button', { name: 'Select shown' }).click()
  await page.getByLabel('Repetitions').selectOption('2')
  await expect(page.getByText(/180 trials planned/)).toBeVisible()
  await expect(page.getByRole('button', { name: 'Run batch' })).toBeDisabled()
})
