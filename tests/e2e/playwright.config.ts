import { defineConfig } from '@playwright/test'

function normalizeSubpath(raw = '/ocis'): string {
  if (!raw || raw === '/') {
    return ''
  }
  return `/${raw.replace(/^\/+/, '').replace(/\/+$/, '')}`
}

const subpath = normalizeSubpath(process.env.E2E_SUBPATH)
const origin = (process.env.E2E_BASE_ORIGIN || 'https://127.0.0.1:9200').replace(/\/+$/, '')
const baseUrl = process.env.E2E_BASE_URL || `${origin}${subpath}`

export default defineConfig({
  testDir: '.',
  timeout: 120_000,
  retries: 1,
  outputDir: 'test-results',
  reporter: [['list'], ['html', { outputFolder: 'playwright-report', open: 'never' }]],
  use: {
    baseURL: baseUrl,
    ignoreHTTPSErrors: true,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure'
  }
})
