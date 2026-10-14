// Per-chat unsent drafts (doc 14): browser-only, never sent to models. Keys are a session ID or
// `new:<folderId|unfiled>`. `pending` keeps the exact request bodies + idempotency keys of a send
// in flight, so a refresh resends the same requests instead of creating duplicates.
import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'
import type { Schemas } from '../api/client'
import { safeStorage } from './safeStorage'

export const DRAFTS_STORAGE_KEY = 'perspective-room:drafts:v1'

export interface PendingSend {
  createKey?: string
  createBody?: Schemas['SessionCreate']
  sessionId?: string
  turnKey?: string
  turnBody?: Schemas['TurnCreate']
  forkKey?: string
  forkBody?: Schemas['ForkCreate']
}

export interface Draft {
  text: string
  control?: Partial<Schemas['TurnControl']>
  referenceIds: string[]
  pending?: PendingSend
}

interface DraftsState {
  drafts: Record<string, Draft>
  get: (key: string) => Draft | undefined
  set: (key: string, patch: Partial<Draft>) => void
  clear: (key: string) => void
}

export const newChatKey = (folderId?: string | null) => `new:${folderId ?? 'unfiled'}`

export const useDrafts = create<DraftsState>()(
  persist(
    (set, get) => ({
      drafts: {},
      get: (key) => get().drafts[key],
      set: (key, patch) =>
        set((s) => {
          const base: Draft = s.drafts[key] ?? { text: '', referenceIds: [] }
          return { drafts: { ...s.drafts, [key]: { ...base, ...patch } } }
        }),
      clear: (key) =>
        set((s) => {
          const next = { ...s.drafts }
          delete next[key]
          return { drafts: next }
        }),
    }),
    {
      name: DRAFTS_STORAGE_KEY,
      version: 1,
      storage: createJSONStorage(() => safeStorage),
      partialize: (s) => ({ drafts: s.drafts }),
    },
  ),
)
