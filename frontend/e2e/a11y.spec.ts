import AxeBuilder from '@axe-core/playwright'
import { expect, type Page, test } from '@playwright/test'
import { seedChat, unique } from './helpers'

// doc 10 accessibility checks: axe per theme, keyboard reachability, reduced motion, 200 % zoom.

async function axe(page: Page) {
  const result = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
    .analyze()
  const serious = result.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
  expect(
    serious.map(
      (v) =>
        `${v.id}: ${v.nodes
          .map((n) => n.target.join(' '))
          .slice(0, 3)
          .join(' | ')}`,
    ),
  ).toEqual([])
}

async function setTheme(page: Page, theme: 'dark' | 'light') {
  await page.getByRole('button', { name: theme === 'dark' ? 'Dark' : 'Light' }).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', theme)
}

for (const theme of ['dark', 'light'] as const) {
  test(`axe finds no serious issues on the main screens (${theme})`, async ({ page }) => {
    const s = await seedChat(page, unique('Axe '))
    await page.goto('/')
    await setTheme(page, theme)
    for (const path of ['/', `/rooms/${s.id}`, '/chats', '/personalities', '/settings', '/lab']) {
      await page.goto(path)
      await page.waitForLoadState('networkidle')
      await axe(page)
    }
    await page.goto(`/rooms/${s.id}`)
    await page.getByRole('button', { name: /Saved ideas/ }).click()
    await axe(page) // the open drawer
  })
}

test('the room is usable with the keyboard alone', async ({ page }) => {
  const s = await seedChat(page, unique('Keyboard '))
  await page.goto(`/rooms/${s.id}`)
  const reached = new Set<string>()
  for (let i = 0; i < 120 && !reached.has('Message'); i++) {
    await page.keyboard.press('Tab')
    const name = await page.evaluate(() => {
      const el = document.activeElement as HTMLElement | null
      const label = (el as HTMLTextAreaElement | null)?.labels?.[0]?.textContent?.trim()
      return el?.getAttribute('aria-label') || label || el?.textContent?.trim() || ''
    })
    reached.add(name)
  }
  for (const control of ['Select all', 'Ask more', 'Challenge', 'Message'])
    expect([...reached]).toContain(control)
  const outline = await page.evaluate(() => getComputedStyle(document.activeElement!).outlineStyle)
  expect(outline).not.toBe('none') // visible focus
  await page.keyboard.type('Sent from the keyboard')
  await page.keyboard.press('Enter')
  await expect(page.getByTestId('user-message').last()).toContainText('Sent from the keyboard')
})

test('reduced motion turns transitions off', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto('/')
  const duration = await page.evaluate(
    () => getComputedStyle(document.querySelector('nav')!).transitionDuration,
  )
  expect(parseFloat(duration)).toBeLessThan(0.02)
})

test('200 % zoom reflows instead of clipping', async ({ page }) => {
  const s = await seedChat(page, unique('Zoom '))
  await page.setViewportSize({ width: 720, height: 450 }) // 1440×900 at 200 %
  await page.goto(`/rooms/${s.id}`)
  await expect(page.getByTestId('contribution')).toHaveCount(3)
  const overflow = await page.evaluate(() => {
    const m = document.getElementById('main')!
    return Math.max(
      document.documentElement.scrollWidth - document.documentElement.clientWidth,
      m.scrollWidth - m.clientWidth,
    )
  })
  expect(overflow).toBeLessThanOrEqual(0)
  await expect(page.getByRole('button', { name: 'Open navigation' })).toBeVisible()
})
