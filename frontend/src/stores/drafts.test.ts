describe('drafts store', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.resetModules()
  })

  it('keeps independent drafts per chat and survives a reload', async () => {
    const { useDrafts, DRAFTS_STORAGE_KEY } = await import('./drafts')
    useDrafts.getState().set('chat-a', { text: 'idea for A' })
    useDrafts.getState().set('chat-b', { text: 'idea for B' })
    vi.resetModules()
    const reloaded = await import('./drafts')
    await reloaded.useDrafts.persist.rehydrate()
    expect(reloaded.useDrafts.getState().get('chat-a')?.text).toBe('idea for A')
    expect(reloaded.useDrafts.getState().get('chat-b')?.text).toBe('idea for B')
    expect(localStorage.getItem(DRAFTS_STORAGE_KEY)).toContain('idea for A')
  })

  it('clears only the requested chat', async () => {
    const { useDrafts } = await import('./drafts')
    useDrafts.getState().set('chat-a', { text: 'a' })
    useDrafts.getState().set('chat-b', { text: 'b' })
    useDrafts.getState().clear('chat-a')
    expect(useDrafts.getState().get('chat-a')).toBeUndefined()
    expect(useDrafts.getState().get('chat-b')?.text).toBe('b')
  })

  it('stores pending request bodies with their keys for an exact resend', async () => {
    const { useDrafts, newChatKey } = await import('./drafts')
    const key = newChatKey()
    useDrafts.getState().set(key, {
      text: 'x',
      pending: { createKey: 'k1', createBody: { idea: 'x' } },
    })
    useDrafts.getState().set(key, {
      pending: { ...useDrafts.getState().get(key)!.pending, sessionId: 's1' },
    })
    expect(useDrafts.getState().get(key)?.pending).toEqual({
      createKey: 'k1',
      createBody: { idea: 'x' },
      sessionId: 's1',
    })
    expect(key).toBe('new:unfiled')
  })
})
