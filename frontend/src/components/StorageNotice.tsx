import { useStorageHealth } from '../stores/safeStorage'

/** Shown when the browser refuses local storage: drafts still work, but only in this tab. */
export function StorageNotice() {
  const failed = useStorageHealth((s) => s.failed)
  if (!failed) return null
  return (
    <p role="status" className="text-[13px] text-warning">
      Not saved on this device — this browser blocked local storage, so drafts last only until this
      tab closes.
    </p>
  )
}
