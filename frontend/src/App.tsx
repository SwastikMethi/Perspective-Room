import { Route, Routes } from 'react-router'
import { AppShell } from './components/AppShell'
import { FolderPage } from './features/folders/FolderPage'
import { LabPage } from './features/lab/LabPage'
import { PersonalitiesPage } from './features/personas/PersonalitiesPage'
import { NewChatPage } from './features/rooms/NewChatPage'
import { RoomRoute } from './features/rooms/RoomPage'
import { SettingsPage } from './features/settings/SettingsPage'
import { ChatsPage } from './features/workspace/ChatsPage'

// Unknown paths render a plain not-found screen inside the shell.
function Screen({ title }: { title: string }) {
  return (
    <section className="mx-auto max-w-[var(--layout-workspace-max)] px-6 py-8 lg:px-12">
      <h1 className="text-[length:var(--text-title)] font-semibold">{title}</h1>
    </section>
  )
}

export function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<NewChatPage />} />
        <Route path="chats" element={<ChatsPage />} />
        <Route path="folders/:folderId" element={<FolderPage />} />
        <Route path="rooms/:id" element={<RoomRoute />} />
        <Route path="personalities" element={<PersonalitiesPage />} />
        <Route path="lab" element={<LabPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<Screen title="Page not found" />} />
      </Route>
    </Routes>
  )
}
