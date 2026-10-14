import { act } from '@testing-library/react'

describe('ui store', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.resetModules()
    vi.restoreAllMocks()
    document.documentElement.dataset.theme = ''
  })

  it('defaults to dark and a collapsed sidebar', async () => {
    const { useUi } = await import('./ui')
    expect(useUi.getState().theme).toBe('dark')
    expect(useUi.getState().sidebarExpanded).toBe(false)
  })

  it('persists theme, sidebar and open folders under the versioned key', async () => {
    const { useUi, UI_STORAGE_KEY } = await import('./ui')
    act(() => {
      useUi.getState().setTheme('light')
      useUi.getState().setSidebarExpanded(true)
      useUi.getState().toggleFolder('f1')
      useUi.getState().setMobileDrawerOpen(true)
    })
    const saved = JSON.parse(localStorage.getItem(UI_STORAGE_KEY)!)
    expect(UI_STORAGE_KEY).toBe('perspective-room:ui:v1')
    expect(saved.state).toEqual({ theme: 'light', sidebarExpanded: true, openFolderIds: ['f1'] })
    expect(document.documentElement.dataset.theme).toBe('light')
  })

  it('keeps working in memory and flags the failure when storage throws', async () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('quota', 'QuotaExceededError')
    })
    const { useUi } = await import('./ui')
    const { useStorageHealth } = await import('./safeStorage')
    act(() => useUi.getState().setTheme('light'))
    expect(useUi.getState().theme).toBe('light')
    expect(useStorageHealth.getState().failed).toBe(true)
  })
})
