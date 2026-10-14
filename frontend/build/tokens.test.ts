// @vitest-environment node
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { tokensCss, type DesignTokens } from './tokens'

const tokens: DesignTokens = JSON.parse(
  readFileSync(
    fileURLToPath(new URL('../../handoff/config/design-tokens.json', import.meta.url)),
    'utf8',
  ),
)

describe('tokensCss', () => {
  const css = tokensCss(tokens)

  it('emits every semantic color for both themes', () => {
    for (const theme of ['dark', 'light'] as const) {
      const block = css.split(`[data-theme="${theme}"]`)[1].split('}')[0]
      for (const [key, value] of Object.entries(tokens.themes[theme])) {
        expect(block).toContain(`--${key.replace(/_/g, '-')}: ${value};`)
      }
      expect(block).toContain(`color-scheme: ${theme};`)
    }
  })

  it('emits layout widths, typography and motion on :root', () => {
    expect(css).toContain('--layout-sidebar-collapsed: 64px;')
    expect(css).toContain('--layout-sidebar-expanded: 272px;')
    expect(css).toContain('--text-body: 16px;')
    expect(css).toContain('--message-measure: 68ch;')
    expect(css).toContain('--doodle-opacity: 0.16;')
  })
})
