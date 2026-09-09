import { test, expect } from '@playwright/test';

test('detect urban basins button completes without error', async ({ page }) => {
  test.setTimeout(180000);
  await page.goto('/map', { waitUntil: 'domcontentloaded' });

  await page.locator('#detect-cluster-btn').click();

  await expect(page.locator('#detect-cluster-btn')).toBeEnabled({ timeout: 120000 });

  await page.waitForFunction(() => {
    const status = document.getElementById('cluster-status')?.textContent || '';
    return status.includes('Détection terminée') || status.includes('Erreur lors de la détection') || status.includes('Aucun cluster détecté');
  }, { timeout: 120000 });

  const status = await page.locator('#cluster-status').textContent();
  expect(status).toContain('Détection terminée');
  expect(status).not.toContain('Erreur lors de la détection');
});
