import { defineConfig, devices } from '@playwright/test'

// Browser walkthrough against the real app (demo providers) on 127.0.0.1:${E2E_PORT:-8010}.
// Feature specs run at 1440×900; the walkthrough and overflow specs run at every doc 10 size.
const port = process.env.E2E_PORT ?? '8010'
const everySize = /(journey|overflow)\.spec\.ts/
export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  timeout: 90_000,
  expect: { timeout: 10_000 },
  reporter: [['list']],
  use: { baseURL: `http://127.0.0.1:${port}`, trace: 'retain-on-failure' },
  webServer: {
    command: 'npm run build && ../scripts/e2e_server.sh',
    url: `http://127.0.0.1:${port}/api/v1/health`,
    reuseExistingServer: false,
    timeout: 180_000,
  },
  projects: [
    {
      name: 'desktop',
      use: { viewport: { width: 1440, height: 900 } },
      testIgnore: /screenshots\.spec\.ts/,
    },
    { name: 'wide', use: { viewport: { width: 1920, height: 1080 } }, testMatch: everySize },
    { name: 'laptop', use: { viewport: { width: 1024, height: 768 } }, testMatch: everySize },
    {
      name: 'mobile',
      use: { ...devices['Pixel 7'], viewport: { width: 390, height: 844 } },
      testMatch: everySize,
    },
    {
      name: 'screenshots',
      use: { viewport: { width: 1440, height: 900 } },
      testMatch: /screenshots\.spec\.ts/,
    },
  ],
})
