import { defineConfig, devices } from '@playwright/test';
import * as path from 'path';

// Статически отдаём корень репозитория (single HTML, без бэкенда).
const repoRoot = path.resolve(__dirname, '..', '..');

export default defineConfig({
  testDir: '.',
  timeout: 30_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  reporter: [['list']],
  use: {
    baseURL: 'http://localhost:8000',
    trace: 'on-first-retry',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    // Требует Python 3 на PATH. Linux/Mac: python3; Windows: python.
    command: (process.platform === 'win32' ? 'python' : 'python3') + ' -m http.server 8000',
    cwd: repoRoot,
    url: 'http://localhost:8000/index.html',
    reuseExistingServer: !process.env.CI,
    timeout: 20_000,
  },
});
