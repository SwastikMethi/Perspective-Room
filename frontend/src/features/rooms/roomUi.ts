// Per-room view state (never persisted): which details tab is open, expanded turn groups, the
// highlighted deep-link target, and a handle to focus the composer from card actions.
import { create } from 'zustand'

export type DrawerTab = 'brief' | 'ideas' | 'sources' | 'summary' | 'run'

interface RoomUi {
  drawer: { tab: DrawerTab; sourceId?: string } | null
  expanded: Record<string, boolean>
  highlight: string | null
  focusComposer: () => void
  openDrawer: (tab: DrawerTab, sourceId?: string) => void
  closeDrawer: () => void
  toggleGroup: (key: string) => void
  reset: () => void
}

export const useRoomUi = create<RoomUi>((set) => ({
  drawer: null,
  expanded: {},
  highlight: null,
  focusComposer: () => {},
  openDrawer: (tab, sourceId) => set({ drawer: { tab, sourceId } }),
  closeDrawer: () => set({ drawer: null }),
  toggleGroup: (key) => set((s) => ({ expanded: { ...s.expanded, [key]: !s.expanded[key] } })),
  reset: () => set({ drawer: null, expanded: {}, highlight: null }),
}))

export const STAGE_TEXT: Record<string, string> = {
  queued: 'Waiting to start',
  preparing: 'Preparing',
  intake: 'Reading your message',
  routing: 'Choosing who speaks next',
  researching: 'Checking current sources',
  drafting: 'Drafting',
  validating: 'Checking the draft',
  assessing: 'Checking fit and constraints',
  repairing: 'Revising once',
  publishing: 'Publishing',
  memory: 'Updating the conversation memory',
  cancelling: 'Stopping',
  finished: 'Finished',
}
