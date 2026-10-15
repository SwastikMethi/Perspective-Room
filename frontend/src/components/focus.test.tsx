import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { DialogHost, dialogs } from './Dialogs'
import { openerOf } from './focus'

test('closing a dialog returns focus to the control that opened it', async () => {
  render(
    <>
      <button
        type="button"
        onClick={() =>
          void dialogs.confirm({ title: 'Delete?', body: 'Sure?', confirmLabel: 'Delete' })
        }
      >
        Open
      </button>
      <DialogHost />
    </>,
  )
  const opener = screen.getByRole('button', { name: 'Open' })
  opener.focus()
  act(() => opener.click())
  expect(await screen.findByRole('dialog')).toBeInTheDocument()
  fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' })
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  expect(document.activeElement).toBe(opener)
})

test('a dialog opened from a menu item returns focus to the menu trigger', () => {
  document.body.innerHTML = `
    <button id="t" aria-controls="m">Actions</button>
    <div role="menu" id="m"><div role="menuitem" tabindex="-1" id="i">Rename</div></div>`
  expect(openerOf(document.getElementById('i'))?.id).toBe('t')
  expect(openerOf(document.getElementById('t'))?.id).toBe('t')
})
