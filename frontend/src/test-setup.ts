import '@testing-library/jest-dom/vitest'

// Node >= 25 exposes its own file-less `localStorage` global that shadows jsdom's Storage.
const dom = (globalThis as { jsdom?: { window: Window } }).jsdom
if (dom && typeof globalThis.localStorage?.clear !== 'function') {
  for (const name of ['localStorage', 'sessionStorage'] as const) {
    Object.defineProperty(globalThis, name, { value: dom.window[name], configurable: true })
  }
}
