import { defineConfig } from '@playwright/test'

// Browser walkthrough against the real app (demo providers) on 127.0.0.1:8010.
export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: [['list']],
  use: { baseURL: 'http://127.0.0.1:8010', trace: 'retain-on-failure' },
  webServer: {
    command: 'npm run build && ../scripts/e2e_server.sh',
    url: 'http://127.0.0.1:8010/api/v1/health',
    reuseExistingServer: false,
    timeout: 180_000,
  },
  projects: [{ name: 'desktop', use: { viewport: { width: 1440, height: 900 } } }],
})
