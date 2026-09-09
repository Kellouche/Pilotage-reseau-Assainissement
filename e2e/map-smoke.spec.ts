import { test, expect } from '@playwright/test';

test('map page loads modular scripts and exposes detection button', async ({ page }) => {
  await page.goto('/map', { waitUntil: 'domcontentloaded' });

  await expect(page.locator('#detect-cluster-btn')).toBeVisible();
  await expect(page.locator('#map-legend')).toHaveCount(0);
  await expect(page.locator('#cluster-progress-bar')).toHaveCount(0);

  await page.evaluate(() => {
    const win = window as typeof window & {
      mapState?: unknown;
      detecterBassins?: unknown;
      chargerDonneesInitiales?: unknown;
    };
    return {
      state: Boolean(win.mapState),
      detecterBassins: typeof win.detecterBassins === 'function',
      chargerDonneesInitiales: typeof win.chargerDonneesInitiales === 'function'
    };
  }).then(result => {
    expect(result.state).toBeTruthy();
    expect(result.detecterBassins).toBeTruthy();
    expect(result.chargerDonneesInitiales).toBeTruthy();
  });
});
