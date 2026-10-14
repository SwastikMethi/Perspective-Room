/** Two overlapping perspectives, as in the approved design. */
export function Logo({ size = 32 }: { size?: number }) {
  return (
    <svg aria-hidden focusable="false" width={size} height={size * 0.7} viewBox="0 0 46 32">
      <circle cx="16" cy="16" r="13" fill="#EB9173" />
      <circle cx="30" cy="16" r="13" fill="var(--muted)" opacity="0.85" />
    </svg>
  )
}
