import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useDrafts } from '../../stores/drafts'
import { Composer, type ComposerProps } from './Composer'

function setup(over: Partial<ComposerProps> = {}) {
  const onSend = vi.fn(async () => {})
  const onTarget = vi.fn(async (id: string) => {
    useDrafts.getState().set('room-1', {
      control: {
        ...useDrafts.getState().get('room-1')?.control,
        audience: 'person',
        target_persona_id: id as 'skeptic',
      },
    })
  })
  render(
    <Composer
      draftKey="room-1"
      personas={[]}
      selected={['mentor', 'skeptic', 'explorer']}
      standard={false}
      running={false}
      ideas={[]}
      onSend={onSend}
      onStop={() => {}}
      onTarget={onTarget}
      {...over}
    />,
  )
  return { onSend, onTarget, box: screen.getByLabelText('Message') }
}

beforeEach(() => {
  localStorage.clear()
  useDrafts.setState({ drafts: {} })
})

test('Enter sends; Shift+Enter and IME composition do not', () => {
  const { onSend, box } = setup()
  fireEvent.change(box, { target: { value: 'An idea' } })
  fireEvent.keyDown(box, { key: 'Enter', shiftKey: true })
  fireEvent.keyDown(box, { key: 'Enter', isComposing: true })
  fireEvent.keyDown(box, { key: 'Enter', keyCode: 229 })
  expect(onSend).not.toHaveBeenCalled()
  fireEvent.keyDown(box, { key: 'Enter' })
  expect(onSend).toHaveBeenCalledWith('An idea', expect.objectContaining({ audience: 'auto' }))
})

test('a failed send keeps the text in the draft', async () => {
  const { box } = setup({ onSend: vi.fn(async () => Promise.reject(new Error('503'))) })
  fireEvent.change(box, { target: { value: 'Keep this' } })
  fireEvent.keyDown(box, { key: 'Enter' })
  await waitFor(() => expect(useDrafts.getState().get('room-1')?.text).toBe('Keep this'))
  expect(box).toHaveValue('Keep this')
})

test('@ autocomplete sets a structured target and removes the typed mention', async () => {
  const { onTarget, box } = setup()
  fireEvent.change(box, { target: { value: 'Hey @ske', selectionStart: 8 } })
  expect(screen.getByRole('listbox', { name: 'Address a perspective' })).toBeInTheDocument()
  fireEvent.keyDown(box, { key: 'Enter' })
  await waitFor(() => expect(onTarget).toHaveBeenCalledWith('skeptic'))
  expect(useDrafts.getState().get('room-1')?.text).toBe('Hey ')
  expect(screen.getByText('To Skeptic')).toBeInTheDocument()
})

test('a referenced idea that was removed keeps the text and asks to reselect', () => {
  useDrafts
    .getState()
    .set('room-1', { text: 'Combine these', control: { idea_card_ids: ['gone'] } })
  setup()
  expect(screen.getByText(/no longer exists — reselect/)).toBeInTheDocument()
  expect(screen.getByLabelText('Message')).toHaveValue('Combine these')
})
