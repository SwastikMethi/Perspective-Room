// Browser-only UI state (doc 14): theme, desktop sidebar, open folders. Never sent to the server.
import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'
import { safeStorage } from './safeStorage'

export type Theme = 'dark' | 'light'
export const UI_STORAGE_KEY = 'perspective-room:ui:v1'

interface UiState {
  theme: Theme
  sidebarExpanded: boolean
  mobileDrawerOpen: boolean
  openFolderIds: string[]
  setTheme: (theme: Theme) => void
  setSidebarExpanded: (expanded: boolean) => void
  setMobileDrawerOpen: (open: boolean) => void
  toggleFolder: (folderId: string) => void
}

export function applyTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme
}

export const useUi = create<UiState>()(
  persist(
    (set) => ({
      theme: 'dark',
      sidebarExpanded: false,
      mobileDrawerOpen: false,
      openFolderIds: [],
      setTheme: (theme) => {
        applyTheme(theme)
        set({ theme })
      },
      setSidebarExpanded: (sidebarExpanded) => set({ sidebarExpanded }),
      setMobileDrawerOpen: (mobileDrawerOpen) => set({ mobileDrawerOpen }),
      toggleFolder: (id) =>
        set((s) => ({
          openFolderIds: s.openFolderIds.includes(id)
            ? s.openFolderIds.filter((f) => f !== id)
            : [...s.openFolderIds, id],
        })),
    }),
    {
      name: UI_STORAGE_KEY,
      version: 1,
      storage: createJSONStorage(() => safeStorage),
      partialize: (s) => ({
        theme: s.theme,
        sidebarExpanded: s.sidebarExpanded,
        openFolderIds: s.openFolderIds,
      }),
      onRehydrateStorage: () => (state) => state && applyTheme(state.theme),
    },
  ),
)
