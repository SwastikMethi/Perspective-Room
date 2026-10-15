import { act, render, screen } from '@testing-library/react'
import { useDrafts } from '../stores/drafts'
import { useStorageHealth } from '../stores/safeStorage'
import { StorageNotice } from './StorageNotice'

afterEach(() => {
  vi.restoreAllMocks()
  useStorageHealth.setState({ failed: false })
})

test('a full or blocked localStorage shows a notice and the draft stays in memory', () => {
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
    throw new DOMException('quota', 'QuotaExceededError')
  })
  render(<StorageNotice />)
  expect(screen.queryByText(/Not saved on this device/)).toBeNull()
  act(() => useDrafts.getState().set('chat-x', { text: 'keep me' }))
  expect(screen.getByRole('status')).toHaveTextContent('Not saved on this device')
  expect(useDrafts.getState().get('chat-x')?.text).toBe('keep me')
})
