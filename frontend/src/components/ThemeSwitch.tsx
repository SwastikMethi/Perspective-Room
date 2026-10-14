import { Moon, Sun } from 'lucide-react'
import { type Theme, useUi } from '../stores/ui'

const OPTIONS: { value: Theme; label: string; Icon: typeof Sun }[] = [
  { value: 'light', label: 'Light', Icon: Sun },
  { value: 'dark', label: 'Dark', Icon: Moon },
]

export function ThemeSwitch() {
  const theme = useUi((s) => s.theme)
  const setTheme = useUi((s) => s.setTheme)
  return (
    <div role="group" aria-label="Color theme" className="flex items-center gap-2">
      {OPTIONS.map(({ value, label, Icon }) => {
        const selected = theme === value
        return (
          <button
            key={value}
            type="button"
            aria-pressed={selected}
            onClick={() => setTheme(value)}
            className={
              'inline-flex min-h-11 items-center gap-2 rounded-control border px-3 text-sm sm:min-h-10 ' +
              (selected
                ? 'border-selection-border bg-selection-surface font-medium text-text'
                : 'border-border text-muted hover:text-text')
            }
          >
            <Icon aria-hidden size={18} />
            <span className="max-sm:sr-only">{label}</span>
          </button>
        )
      })}
    </div>
  )
}
