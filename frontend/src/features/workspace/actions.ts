// Chat and folder organization actions (doc 14). Organization edits never touch model context;
// every failure is shown and leaves the previous state in place.
import type { QueryClient } from '@tanstack/react-query'
import { ApiError, api, type Schemas, unwrap } from '../../api/client'
import { keys } from '../../api/queries'
import { dialogs, notify } from '../../components/Dialogs'
import { useDrafts } from '../../stores/drafts'
import { withOperationKey } from '../rooms/send'

export type ChatSummary = Pick<
  Schemas['SessionSummary'],
  | 'id'
  | 'title'
  | 'folder_id'
  | 'is_pinned'
  | 'is_archived'
  | 'organization_version'
  | 'active_run_id'
>

const message = (e: unknown) =>
  e instanceof ApiError ? e.error.message : 'That did not work. Try again.'

async function refreshLists(qc: QueryClient, sessionId?: string) {
  await Promise.all([
    qc.invalidateQueries({ queryKey: ['history'] }),
    qc.invalidateQueries({ queryKey: keys.folders }),
    sessionId ? qc.invalidateQueries({ queryKey: keys.session(sessionId) }) : null,
  ])
}

export async function organize(
  qc: QueryClient,
  chat: ChatSummary,
  patch: Omit<Schemas['SessionOrganizationPatch'], 'expected_organization_version'>,
): Promise<boolean> {
  try {
    await unwrap(
      api.PATCH('/api/v1/sessions/{session_id}/organization', {
        params: { path: { session_id: chat.id } },
        body: { expected_organization_version: chat.organization_version, ...patch },
      }),
    )
    return true
  } catch (e) {
    notify(
      e instanceof ApiError && e.code === 'version_conflict'
        ? 'This chat changed elsewhere; the list is refreshed. Try again.'
        : e instanceof ApiError && e.code === 'folder_missing'
          ? 'That folder no longer exists; the chat stays where it was.'
          : message(e),
      'error',
    )
    return false
  } finally {
    await refreshLists(qc, chat.id)
  }
}

export async function renameChat(qc: QueryClient, chat: ChatSummary) {
  const title = await dialogs.prompt({
    title: 'Rename chat',
    label: 'Chat name',
    initial: chat.title,
    confirmLabel: 'Rename',
    maxLength: 120,
  })
  if (title && title !== chat.title) await organize(qc, chat, { title })
}

export async function moveChat(qc: QueryClient, chat: ChatSummary, folders: Schemas['Folder'][]) {
  const choice = await dialogs.choose({
    title: 'Move to folder',
    options: [
      { value: '', label: 'No folder' },
      ...folders.map((f) => ({ value: f.id, label: f.name })),
    ],
    initial: chat.folder_id ?? '',
    confirmLabel: 'Move',
  })
  if (choice === null || choice === (chat.folder_id ?? '')) return
  await organize(qc, chat, { folder_id: choice || null })
}

export async function setArchived(qc: QueryClient, chat: ChatSummary, archived: boolean) {
  const ok = await organize(qc, chat, { is_archived: archived })
  if (ok) notify(archived ? 'Chat archived. Find it under Archived.' : 'Chat restored.')
}

export async function duplicateChat(qc: QueryClient, chat: ChatSummary): Promise<string | null> {
  try {
    const session = await unwrap(
      api.GET('/api/v1/sessions/{session_id}', { params: { path: { session_id: chat.id } } }),
    )
    const result = await withOperationKey(`dup:${chat.id}`, (key) =>
      unwrap(
        api.POST('/api/v1/sessions/{session_id}/forks', {
          params: {
            path: { session_id: chat.id },
            header: { 'Idempotency-Key': key },
          },
          body: {
            expected_version: session.version,
            through_message_id: null,
            title: `Copy of ${chat.title}`.slice(0, 120),
            purpose: 'fork',
          },
        }),
      ),
    )
    await refreshLists(qc)
    notify('Copy created.')
    return result.session.id
  } catch (e) {
    notify(message(e), 'error')
    return null
  }
}

export async function exportChat(chat: { id: string; title: string }, format: 'markdown' | 'json') {
  try {
    const r = await fetch(`/api/v1/sessions/${chat.id}/export?format=${format}`)
    if (!r.ok) {
      const body = await r.json().catch(() => null)
      throw new ApiError(r.status, body ?? { code: 'http_error', message: 'Export failed.' })
    }
    const name =
      /filename="([^"]+)"/.exec(r.headers.get('content-disposition') ?? '')?.[1] ??
      `chat.${format === 'json' ? 'json' : 'md'}`
    const url = URL.createObjectURL(await r.blob())
    const a = document.createElement('a')
    a.href = url
    a.download = name
    a.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch (e) {
    notify(message(e), 'error')
  }
}

/** Permanent local deletion; clears only this chat's draft. Returns true when deleted. */
export async function deleteChat(qc: QueryClient, chat: ChatSummary): Promise<boolean> {
  const ok = await dialogs.confirm({
    title: `Delete “${chat.title}”?`,
    body: 'This permanently removes the chat, its replies, saved ideas and sources from this computer. It cannot be undone.',
    confirmLabel: 'Delete chat',
    danger: true,
  })
  if (!ok) return false
  try {
    await unwrap(
      api.DELETE('/api/v1/sessions/{session_id}', { params: { path: { session_id: chat.id } } }),
    )
    useDrafts.getState().clear(chat.id)
    qc.removeQueries({ queryKey: keys.session(chat.id) })
    qc.removeQueries({ queryKey: keys.messages(chat.id) })
    notify('Chat deleted.')
    return true
  } catch (e) {
    notify(
      e instanceof ApiError && e.code === 'run_active'
        ? 'Stop the running reply before deleting this chat.'
        : message(e),
      'error',
    )
    return false
  } finally {
    await refreshLists(qc)
  }
}

// ---------- folders ----------

export async function createFolder(qc: QueryClient): Promise<Schemas['Folder'] | null> {
  const name = await dialogs.prompt({
    title: 'New folder',
    label: 'Folder name',
    confirmLabel: 'Create folder',
    maxLength: 80,
  })
  if (!name) return null
  try {
    const folder = await withOperationKey(`folder:${name.toLowerCase()}`, (key) =>
      unwrap(
        api.POST('/api/v1/folders', {
          params: { header: { 'Idempotency-Key': key } },
          body: { name },
        }),
      ),
    )
    await refreshLists(qc)
    return folder
  } catch (e) {
    notify(message(e), 'error')
    return null
  }
}

export async function renameFolder(qc: QueryClient, folder: Schemas['Folder']) {
  const name = await dialogs.prompt({
    title: 'Rename folder',
    label: 'Folder name',
    initial: folder.name,
    confirmLabel: 'Rename',
    maxLength: 80,
  })
  if (!name || name === folder.name) return
  try {
    await unwrap(
      api.PATCH('/api/v1/folders/{folder_id}', {
        params: { path: { folder_id: folder.id } },
        body: { expected_version: folder.version, name },
      }),
    )
  } catch (e) {
    notify(message(e), 'error')
  } finally {
    await refreshLists(qc)
  }
}

export async function deleteFolder(qc: QueryClient, folder: Schemas['Folder']): Promise<boolean> {
  const total = folder.chat_count + folder.archived_chat_count
  const ok = await dialogs.confirm({
    title: `Delete folder “${folder.name}”?`,
    body:
      total > 0
        ? `The ${total === 1 ? 'chat' : `${total} chats`} inside will be kept and moved to No folder.`
        : 'The folder is empty. No chats are affected.',
    confirmLabel: 'Delete folder',
    danger: true,
  })
  if (!ok) return false
  try {
    await unwrap(
      api.DELETE('/api/v1/folders/{folder_id}', {
        params: { path: { folder_id: folder.id }, query: { expected_version: folder.version } },
      }),
    )
    notify('Folder deleted. Its chats are kept.')
    return true
  } catch (e) {
    notify(message(e), 'error')
    return false
  } finally {
    await refreshLists(qc)
  }
}
