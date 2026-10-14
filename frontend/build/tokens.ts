// Design tokens: handoff/config/design-tokens.json is the single source; this turns it into CSS
// variables served as the virtual module `virtual:tokens.css` (render-blocking, so no theme flash).
import { readFileSync } from 'node:fs'
import type { Plugin } from 'vite'

export interface DesignTokens {
  themes: Record<'dark' | 'light', Record<string, string>>
  typography: {
    font_family: string
    body_px: number
    small_px: number
    title_px: number
    line_height: number
    message_max_width_ch: number
  }
  layout_px: Record<string, number>
  radius_px: Record<string, number>
  motion: { duration_ms: number }
  illustration: { decorative_art_max_opacity: number }
}

const kebab = (s: string) => s.replace(/_/g, '-')

export function tokensCss(t: DesignTokens): string {
  const root = [
    `--font-family: ${t.typography.font_family};`,
    `--text-body: ${t.typography.body_px}px;`,
    `--text-small: ${t.typography.small_px}px;`,
    `--text-title: ${t.typography.title_px}px;`,
    `--line-height: ${t.typography.line_height};`,
    `--message-measure: ${t.typography.message_max_width_ch}ch;`,
    ...Object.entries(t.layout_px).map(([k, v]) => `--layout-${kebab(k)}: ${v}px;`),
    ...Object.entries(t.radius_px).map(([k, v]) => `--radius-${kebab(k)}: ${v}px;`),
    `--motion-duration: ${t.motion.duration_ms}ms;`,
    `--doodle-opacity: ${t.illustration.decorative_art_max_opacity};`,
  ]
  const theme = (name: 'dark' | 'light') =>
    `[data-theme="${name}"] {\n  color-scheme: ${name};\n` +
    Object.entries(t.themes[name])
      .map(([k, v]) => `  --${kebab(k)}: ${v};`)
      .join('\n') +
    '\n}'
  return `:root {\n  ${root.join('\n  ')}\n}\n${theme('dark')}\n${theme('light')}\n`
}

export function tokensPlugin(path: string): Plugin {
  const id = 'virtual:tokens.css'
  const resolved = '\0virtual:tokens.css'
  return {
    name: 'design-tokens',
    resolveId: (source) => (source === id ? resolved : undefined),
    load(loadId) {
      if (loadId !== resolved) return undefined
      this.addWatchFile(path)
      return tokensCss(JSON.parse(readFileSync(path, 'utf8')))
    },
  }
}
