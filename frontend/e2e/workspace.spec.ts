import { expect, test } from '@playwright/test'
import { call, control, expandedSidebar, seedChat, unique, waitIdle } from './helpers'

test.beforeEach(async ({ page }) => expandedSidebar(page))

test('folders: create, new chat here, move out, delete keeps the chat (T26, T27)', async ({
  page,
}) => {
  await page.goto('/')
  const name = unique('Garden ')
  await page.getByRole('button', { name: 'New folder' }).click()
  await page.getByLabel('Folder name').fill(name)
  await page.getByRole('button', { name: 'Create folder' }).click()
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(name)
  await expect(page.getByText('No chats yet')).toBeVisible()

  await page.getByRole('link', { name: 'New chat here' }).click()
  await expect(page.getByText(`In ${name}`)).toBeVisible()
  const idea = unique('Compost swap ')
  await page.getByLabel('Your idea').fill(idea)
  await page.getByRole('button', { name: 'Send', exact: true }).click()
  await expect(page).toHaveURL(/\/rooms\//)
  await expect(page.getByTestId('contribution')).toHaveCount(3)
  await expect(
    page.getByRole('navigation', { name: 'Breadcrumb' }).getByRole('link', { name }),
  ).toBeVisible()

  // Open the folder in the sidebar: the chat is its child.
  await page.getByRole('button', { name: `Open ${name}` }).click()
  const children = page.getByRole('group', { name: `Chats in ${name}` })
  await expect(children.getByRole('link')).toHaveCount(1)

  // Move to No folder through the row menu.
  await children.getByRole('button', { name: /^Actions for / }).click()
  await page.getByRole('menuitem', { name: 'Move to folder…' }).click()
  await page.getByRole('radio', { name: 'No folder' }).check()
  await page.getByRole('button', { name: 'Move' }).click()
  await expect(page.getByText('No chats yet ·')).toBeVisible()

  // Delete the folder: the confirmation says chats are kept, and the chat survives.
  await page.getByRole('button', { name: `Actions for folder ${name}` }).click()
  await page.getByRole('menuitem', { name: 'Delete folder…' }).click()
  await expect(page.getByRole('dialog')).toContainText(/kept|No chats are affected/)
  await page.getByRole('button', { name: 'Delete folder' }).click()
  await expect(page.getByRole('button', { name: `Open ${name}` })).toHaveCount(0)
  await page.goto('/chats')
  await expect(page.getByRole('main').getByText(idea.slice(0, 20))).toBeVisible()
})

test('search finds a message, deep-links to it, and shows honest empty states (T29)', async ({
  page,
}) => {
  const word = unique('zebrafish')
  const s = await seedChat(page, 'A chat about aquariums')
  const v = (await call(page, 'GET', `/api/v1/sessions/${s.id}`)).version
  await call(page, 'POST', `/api/v1/sessions/${s.id}/turns`, {
    expected_version: v,
    message: `Should we try ${word} first?`,
    control: control(),
  })
  await waitIdle(page, s.id)
  await page.goto('/chats')
  await page.keyboard.press('ControlOrMeta+k')
  const box = page.getByRole('textbox', { name: 'Search chats' })
  await box.fill(word)
  const result = page.getByRole('dialog').getByRole('link').first()
  await expect(result).toContainText(word)
  await result.click()
  await expect(page).toHaveURL(new RegExp(`/rooms/${s.id}\\?message=`))
  const target = page.locator('[data-testid="user-message"].ring-2')
  await expect(target).toContainText(word)
  await expect(target).toBeInViewport()

  await page.keyboard.press('ControlOrMeta+k')
  await box.fill(unique('nothingmatches'))
  await expect(page.getByText(/No chats match/)).toBeVisible()
  await expect(page.getByLabel('Include archived')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Clear search' })).toBeVisible()
})

test('drafts stay per chat across switching and reload; deleting clears only that draft (T30/T31)', async ({
  page,
}) => {
  const a = await seedChat(page, unique('Chat A '))
  const b = await seedChat(page, unique('Chat B '))
  await page.goto(`/rooms/${a.id}`)
  await page.getByLabel('Message', { exact: true }).fill('draft for A')
  await page.goto(`/rooms/${b.id}`)
  await page.getByLabel('Message', { exact: true }).fill('draft for B')
  await page.reload()
  await expect(page.getByLabel('Message', { exact: true })).toHaveValue('draft for B')
  await page.goto(`/rooms/${a.id}`)
  await expect(page.getByLabel('Message', { exact: true })).toHaveValue('draft for A')

  await page.getByRole('button', { name: 'Chat options' }).click()
  await page.getByRole('menuitem', { name: 'Organize…' }).click()
  await page.getByRole('menuitem', { name: 'Delete…' }).click()
  await page.getByRole('button', { name: 'Delete chat' }).click()
  await expect(page).toHaveURL(/\/$/)
  const drafts = await page.evaluate(() => localStorage.getItem('perspective-room:drafts:v1') ?? '')
  expect(drafts).not.toContain('draft for A')
  expect(drafts).toContain('draft for B')
})

test('archive makes a chat read-only until restored', async ({ page }) => {
  const s = await seedChat(page, unique('Archive me '))
  const chat = await call(page, 'GET', `/api/v1/sessions/${s.id}`)
  await call(page, 'PATCH', `/api/v1/sessions/${s.id}/organization`, {
    expected_organization_version: chat.organization_version,
    is_archived: true,
  })
  await page.goto('/chats?filter=archived')
  await expect(
    page.getByRole('main').getByRole('link', { name: new RegExp(chat.title.slice(0, 12)) }),
  ).toBeVisible()
  await page.goto(`/rooms/${s.id}`)
  await expect(page.getByRole('status').filter({ hasText: /This chat is archived/ })).toBeVisible()
  await expect(page.getByLabel('Message', { exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: 'Restore' }).click()
  await expect(page.getByLabel('Message', { exact: true })).toBeVisible()
})
