import { Route, Routes } from 'react-router'
import { AppShell } from './components/AppShell'

// ponytail: screens land feature by feature (Tasks 11, 22–26); every route already resolves.
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
        <Route index element={<Screen title="What would you like to think through?" />} />
        <Route path="chats" element={<Screen title="Chats" />} />
        <Route path="folders/:folderId" element={<Screen title="Folder" />} />
        <Route path="rooms/:id" element={<Screen title="Room" />} />
        <Route path="personalities" element={<Screen title="Personalities" />} />
        <Route path="lab" element={<Screen title="Experiment Lab" />} />
        <Route path="settings" element={<Screen title="Settings" />} />
        <Route path="*" element={<Screen title="Page not found" />} />
      </Route>
    </Routes>
  )
}
