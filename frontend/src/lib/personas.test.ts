import { byRoster, shortLabel, spriteStyle } from './personas'

test('sprite math crops the mentor square at 64px (s = 64/108)', () => {
  const style = spriteStyle('mentor', 64, 'dark')!
  const s = 64 / 108
  expect(style.backgroundSize).toBe(`${1586 * s}px ${992 * s}px`)
  expect(style.backgroundPosition).toBe(`${-164 * s}px ${-298 * s}px`)
  expect(style.width).toBe(64)
  expect(style.backgroundImage).toContain('dark')
  expect(spriteStyle('mentor', 32, 'light')!.backgroundImage).toContain('light')
})

test('labels and roster order follow persona-ui.json', () => {
  expect(shortLabel('customer')).toBe('Advocate')
  expect(shortLabel(null)).toBe('Assistant')
  expect(byRoster(['health', 'mentor', 'civic'])).toEqual(['mentor', 'civic', 'health'])
})
