import { spriteStyle } from '../lib/personas'
import { useUi } from '../stores/ui'

/** Decorative portrait (the visible name beside it is the accessible label). */
export function PersonaAvatar({ id, size = 32 }: { id: string; size?: number }) {
  const theme = useUi((s) => s.theme)
  const style = spriteStyle(id, size, theme)
  return (
    <span
      aria-hidden
      data-persona-avatar={id}
      className="inline-block shrink-0 overflow-hidden rounded-full bg-surface-subtle"
      style={style ?? { width: size, height: size }}
    />
  )
}
