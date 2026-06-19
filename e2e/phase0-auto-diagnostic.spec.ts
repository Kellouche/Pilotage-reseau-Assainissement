import { test, expect, Page } from '@playwright/test';

async function waitForDiagnosticReady(page: Page) {
  await page.waitForFunction(() => {
    const score = document.getElementById('global-score')?.textContent || '';
    const total = document.getElementById('total-anomalies')?.textContent || '';
    const modal = document.getElementById('diagnostic-modal');
    const modalHidden = !modal || modal.style.display === 'none';
    return /^\d+(\.\d+)?%$/.test(score) && /^\d+$/.test(total) && modalHidden;
  }, { timeout: 60000 });
}

test.describe('Phase 0 - Auto-diagnostic qualité', () => {
  test('chargement carte et lancement analyse qualité automatique', async ({ page }) => {
    await page.goto('/carte', { waitUntil: 'domcontentloaded' });

    await page.waitForSelector('#loading', { state: 'visible' });

    await page.waitForFunction(() => {
      const el = document.querySelector('.notification');
      return el && el.textContent && el.textContent.includes('Carte prête');
    }, { timeout: 15000 });

    await waitForDiagnosticReady(page);

    const scoreText = await page.textContent('#global-score');
    expect(scoreText).toMatch(/\d+/);

    await page.waitForFunction(() => {
      const el = document.getElementById('loading');
      return el && el.style.display === 'none';
    }, { timeout: 10000 });
  });

  test('modal correction change selon type anomalie', async ({ page }) => {
    await page.goto('/carte', { waitUntil: 'domcontentloaded' });

    await waitForDiagnosticReady(page);

    await page.waitForFunction(() => {
      const select = document.getElementById('select-anomalies-connexions');
      return !!select && select.options.length > 1;
    }, { timeout: 10000 });

    await page.selectOption('#select-anomalies-connexions', { index: 1 });

    await page.waitForSelector('#correction-modal', { state: 'visible', timeout: 10000 });

    const formConnexion = await page.isHidden('#form-connexion');
    expect(formConnexion).toBe(false);
  });
});