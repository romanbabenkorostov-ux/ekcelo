import { defineConfig, devices } from '@playwright/test';
import * as path from 'path';

// Статически отдаём каталог viewer/ (S3: index.html/sw.js/v2961.html переехали туда).
const repoRoot = path.resolve(__dirname, '..', '..', 'viewer');

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
