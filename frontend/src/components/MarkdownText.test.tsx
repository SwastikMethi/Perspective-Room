import { render, screen } from '@testing-library/react'
import { MarkdownText, safeUrl } from './MarkdownText'

test('only http(s) links survive; raw HTML is not rendered', () => {
  expect(safeUrl('javascript:alert(1)')).toBe('')
  expect(safeUrl('https://example.org/a')).toBe('https://example.org/a')
  const { container } = render(
    <MarkdownText
      text={'[ok](https://example.org) [bad](javascript:alert(1)) <img src=x onerror=alert(1)>'}
    />,
  )
  expect(screen.getByRole('link', { name: 'ok' })).toHaveAttribute('rel', 'noopener noreferrer')
  expect(screen.queryByRole('link', { name: 'bad' })).toBeNull()
  expect(container.querySelector('img')).toBeNull()
})

test('fenced code gets a copy-code control', () => {
  render(<MarkdownText text={'```\nnpm test\n```'} />)
  expect(screen.getByRole('button', { name: 'Copy code' })).toBeInTheDocument()
  expect(screen.getByText('npm test')).toBeInTheDocument()
})
