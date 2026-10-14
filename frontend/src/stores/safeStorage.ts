// localStorage that never breaks the app: values always live in memory too, and a failure
// (private mode, quota) flips `failed` so the UI can say "Not saved on this device".
import { create } from 'zustand'
import type { StateStorage } from 'zustand/middleware'

export const useStorageHealth = create<{ failed: boolean }>(() => ({ failed: false }))

const memory = new Map<string, string>()
const fail = () => useStorageHealth.setState({ failed: true })

export const safeStorage: StateStorage = {
  getItem(name) {
    if (memory.has(name)) return memory.get(name) ?? null
    try {
      return window.localStorage.getItem(name)
    } catch {
      fail()
      return null
    }
  },
  setItem(name, value) {
    memory.set(name, value)
    try {
      window.localStorage.setItem(name, value)
    } catch {
      fail()
    }
  },
  removeItem(name) {
    memory.delete(name)
    try {
      window.localStorage.removeItem(name)
    } catch {
      fail()
    }
  },
}
