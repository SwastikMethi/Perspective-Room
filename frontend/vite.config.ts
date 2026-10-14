/// <reference types="vitest/config" />
import { fileURLToPath } from 'node:url'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import { tokensPlugin } from './build/tokens'

const handoff = fileURLToPath(new URL('../handoff', import.meta.url))

export default defineConfig({
  plugins: [react(), tailwindcss(), tokensPlugin(`${handoff}/config/design-tokens.json`)],
  resolve: { alias: { '@handoff': handoff } },
  server: {
    host: '127.0.0.1',
    port: 5173,
    // The browser Origin passes through: add http://localhost:5173 to APP_ALLOWED_ORIGINS for dev.
    proxy: { '/api': { target: 'http://127.0.0.1:8000' } },
    fs: { allow: ['..'] },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test-setup.ts'],
    include: ['src/**/*.test.{ts,tsx}', 'build/**/*.test.ts'],
  },
})
