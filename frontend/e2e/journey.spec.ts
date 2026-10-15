import { expect, type Page, test } from '@playwright/test'
import { unique } from './helpers'

// doc 10 §Browser walkthrough, end to end, at every configured viewport.

const narrow = (page: Page) => (page.viewportSize()?.width ?? 1440) < 900

async function lastGroup(page: Page) {
  return page.getByRole('region', { name: 'Turn', exact: true }).last()
}

async function send(page: Page, text: string) {
  const box = page.getByLabel('Message', { exact: true })
  await box.fill(text)
  await page.getByRole('button', { name: 'Send', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Send', exact: true })).toBeVisible({
    timeout: 20_000,
  })
}

async function chatMenu(page: Page, item: RegExp | string) {
  await page.getByRole('button', { name: 'Chat options' }).click()
  await page.getByRole('menuitem', { name: item }).click()
}

test('the full journey works in both themes and both navigation states', async ({ page }) => {
  // Browse the catalog: all eight profiles.
  await page.goto('/personalities')
  await expect(page.getByRole('button', { name: /^Ask .* directly$/ })).toHaveCount(8)

  // Start with the default trio.
  await page.goto('/')
  const idea = unique('A repair café for the neighborhood ')
  await page.getByLabel('Your idea').fill(idea)
  await page.getByRole('button', { name: 'Send', exact: true }).click()
  await expect(page).toHaveURL(/\/rooms\//)
  await expect(page.getByTestId('contribution')).toHaveCount(3, { timeout: 20_000 })
  const roomUrl = page.url()

  // Ask one person.
  const skeptic = page.locator('[data-testid="contribution"][data-persona="skeptic"]').first()
  await skeptic.getByRole('button', { name: 'Ask more' }).click()
  await send(page, 'What would make this fail first?')
  await expect((await lastGroup(page)).getByTestId('contribution')).toHaveCount(1)

  // Full panel of eight.
  await page.getByRole('button', { name: 'Select all' }).click()
  await expect(page.getByText('8 selected · 8 available')).toBeVisible()
  await page.getByRole('combobox', { name: 'Who answers' }).selectOption('panel')
  await send(page, 'Everyone: one first step each.')
  await expect((await lastGroup(page)).getByTestId('contribution')).toHaveCount(8)

  // Inspect a source from a forced-research turn.
  await page.getByRole('combobox', { name: 'Research' }).selectOption('force')
  await send(page, 'What does existing research say about repair events?')
  const cited = (await lastGroup(page)).getByRole('button', { name: /^\d+ sources?$/ }).first()
  await cited.click()
  const drawer = page.getByRole('dialog', { name: 'Chat details' })
  await expect(drawer.getByText(/demo fixture, not live research/).first()).toBeVisible()
  await drawer.getByRole('button', { name: 'Close details' }).click()

  // Pin two ideas, then combine them.
  const cards = (await lastGroup(page)).getByTestId('contribution')
  await cards
    .nth(0)
    .getByRole('button', { name: /^Save idea/ })
    .click()
  await cards
    .nth(1)
    .getByRole('button', { name: /^Save idea/ })
    .click()
  await expect(page.getByRole('button', { name: /Saved ideas/ })).toContainText('(2)')
  await page.getByRole('button', { name: /Saved ideas/ }).click()
  for (const box of await drawer.getByRole('listitem').getByRole('checkbox').all())
    await box.check()
  await drawer.getByRole('button', { name: 'Combine selected (2)' }).click()
  await expect(page.getByText('Move: Combine')).toBeVisible()
  await page.getByRole('combobox', { name: 'Who answers' }).selectOption('auto')
  await send(page, 'Combine these two into one plan.')
  await expect((await lastGroup(page)).getByTestId('contribution').first()).toBeVisible()

  // Change the brief after a completed round.
  await chatMenu(page, 'Brief')
  await drawer.getByRole('button', { name: 'Edit brief' }).click()
  await drawer.getByLabel('Constraints, one per line').fill('Run it with volunteers only')
  await drawer.getByRole('button', { name: 'Save as new revision' }).click()
  await expect(drawer.getByText(/revision 2/)).toBeVisible()
  await drawer.getByRole('button', { name: 'Close details' }).click()

  // Summarize.
  await chatMenu(page, 'Summarize')
  await expect(page.getByTestId('summary')).toHaveCount(1, { timeout: 20_000 })

  // Export.
  const download = page.waitForEvent('download')
  await chatMenu(page, 'Export as Markdown')
  expect((await download).suggestedFilename()).toMatch(/\.md$/)

  // Reopen after refresh: the same transcript, once.
  const count = await page.getByTestId('contribution').count()
  await page.reload()
  await expect(page.getByTestId('contribution')).toHaveCount(count)

  // Light theme persists across a reload.
  await page.getByRole('button', { name: 'Light' }).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light')
  await page.reload()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light')
  await expect(page.getByRole('button', { name: 'Light' })).toHaveAttribute('aria-pressed', 'true')

  // Navigation in both states.
  if (narrow(page)) {
    await page.getByRole('button', { name: 'Open navigation' }).click()
    const nav = page.getByRole('dialog', { name: 'Navigation' })
    await expect(nav.getByRole('link', { name: 'All chats' })).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(nav).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Open navigation' })).toBeFocused()
  } else {
    await page.getByRole('button', { name: 'Expand sidebar' }).click()
    await expect(page.getByRole('button', { name: 'Collapse sidebar' })).toHaveAttribute(
      'aria-expanded',
      'true',
    )
    await expect(page.getByTestId('contribution')).toHaveCount(count) // transcript survives the toggle
    await page.getByRole('button', { name: 'Collapse sidebar' }).click()
    await expect(page.getByRole('button', { name: 'Expand sidebar' })).toBeVisible()
  }

  // Fork into a new chat; the source keeps its history.
  await chatMenu(page, 'Fork chat…')
  await page.getByRole('radio', { name: 'Fixed panel' }).check()
  await page.getByRole('button', { name: 'Create fork' }).click()
  await expect(page).not.toHaveURL(roomUrl)
  await expect(page.getByRole('link', { name: 'Branched from another chat' })).toBeVisible()
  await expect(page.getByTestId('contribution')).toHaveCount(count)
})
