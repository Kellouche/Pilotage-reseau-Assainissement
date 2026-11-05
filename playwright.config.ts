import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  timeout: 30000,
  use: {
    baseURL: 'http://localhost:5002',
    viewport: { width: 1280, height: 720 },
  },
  webServer: {
    command: '.venv\\Scripts\\python.exe run_server.py',
    port: 5002,
    timeout: 120000,
    reuseExistingServer: true,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});