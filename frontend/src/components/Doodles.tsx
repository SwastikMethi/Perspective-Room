/** Quiet speech-bubble doodle from the approved design. Decorative only; gone below 640px. */
export function Doodles({ className = '' }: { className?: string }) {
  return (
    <svg
      aria-hidden
      focusable="false"
      viewBox="0 0 300 110"
      className={'pointer-events-none hidden select-none sm:block ' + className}
      style={{ opacity: 'var(--doodle-opacity)' }}
      fill="none"
      strokeWidth={3}
      strokeLinecap="round"
    >
      <path
        d="M20 40c0-18 16-30 38-30s38 12 38 30-16 30-38 30c-6 0-11-1-16-3l-14 12 4-16C24 58 20 50 20 40z"
        stroke="#A5BC97"
      />
      <path
        d="M70 52c0-17 15-28 35-28s35 11 35 28-15 28-35 28l-6 0 8 14-16-12c-12-4-21-15-21-30z"
        stroke="#EB9173"
      />
      <path d="M118 10l6-10M132 16l10-6" stroke="#EB9173" />
      <path d="M160 70c30-6 40-30 30-38-8-6-16 6-8 18 14 20 60 22 116 4" stroke="currentColor" />
    </svg>
  )
}
