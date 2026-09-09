# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: phase0-auto-diagnostic.spec.ts >> Phase 0 - Auto-diagnostic qualité >> modal correction change selon type anomalie
- Location: e2e\phase0-auto-diagnostic.spec.ts:35:7

# Error details

```
Test timeout of 30000ms exceeded.
```

```
Error: page.waitForFunction: Test timeout of 30000ms exceeded.
```

# Page snapshot

```yaml
- generic [active] [ref=e1]:
  - generic [ref=e2]:
    - generic [ref=e3]:
      - generic [ref=e4]: Carte opérationnelle - Qualité réseau
      - generic [ref=e5]:
        - generic [ref=e6]:
          - generic [ref=e7]: "Score:"
          - generic [ref=e8]: "--"
        - generic [ref=e9]:
          - generic [ref=e10]: "Anomalies:"
          - generic [ref=e11]: "--"
    - generic [ref=e12]:
      - complementary [ref=e13]:
        - generic [ref=e14]:
          - generic [ref=e15]: Diagnostic qualité
          - button "Masquer le panneau" [ref=e16] [cursor=pointer]: ◀
        - generic [ref=e19]:
          - generic [ref=e20]:
            - button "Connexions" [ref=e21] [cursor=pointer]
            - button "Géométrie" [ref=e22] [cursor=pointer]
            - button "Données" [ref=e23] [cursor=pointer]
            - button "Topologie" [ref=e24] [cursor=pointer]
          - generic [ref=e27]:
            - heading "Diagnostic connexions" [level=4] [ref=e28]
            - generic [ref=e29]: Veuillez cocher les cases pour lancer l'analyse.
            - generic [ref=e30]:
              - generic [ref=e31]:
                - checkbox "Connexions manquantes (Amont/Aval)" [checked] [ref=e32]
                - strong [ref=e33]: Connexions manquantes (Amont/Aval)
              - generic [ref=e34]:
                - checkbox "Incohérences de profondeur (Sauts)" [checked] [ref=e35]
                - strong [ref=e36]: Incohérences de profondeur (Sauts)
      - main [ref=e37]:
        - generic [ref=e38]:
          - generic:
            - generic [ref=e39]:
              - button "Zoom in" [ref=e40] [cursor=pointer]: +
              - button "Zoom out" [ref=e41] [cursor=pointer]: −
            - generic [ref=e42]:
              - link "Leaflet" [ref=e43] [cursor=pointer]:
                - /url: https://leafletjs.com
                - img [ref=e44]
                - text: Leaflet
              - text: "| © OpenStreetMap contributors"
        - generic [ref=e48]: "Zoom: 13"
  - generic [ref=e49]:
    - strong [ref=e50]: "Erreur:"
    - text: "Impossible de charger les données: Failed to fetch"
```

# Test source

```ts
  1  | import { test, expect, Page } from '@playwright/test';
  2  | 
  3  | async function waitForDiagnosticReady(page: Page) {
> 4  |   await page.waitForFunction(() => {
     |              ^ Error: page.waitForFunction: Test timeout of 30000ms exceeded.
  5  |     const score = document.getElementById('global-score')?.textContent || '';
  6  |     const total = document.getElementById('total-anomalies')?.textContent || '';
  7  |     const modal = document.getElementById('diagnostic-modal');
  8  |     const modalHidden = !modal || modal.style.display === 'none';
  9  |     return /^\d+(\.\d+)?%$/.test(score) && /^\d+$/.test(total) && modalHidden;
  10 |   }, { timeout: 60000 });
  11 | }
  12 | 
  13 | test.describe('Phase 0 - Auto-diagnostic qualité', () => {
  14 |   test('chargement carte et lancement analyse qualité automatique', async ({ page }) => {
  15 |     await page.goto('/carte', { waitUntil: 'domcontentloaded' });
  16 | 
  17 |     await page.waitForSelector('#loading', { state: 'visible' });
  18 | 
  19 |     await page.waitForFunction(() => {
  20 |       const el = document.querySelector('.notification');
  21 |       return el && el.textContent && el.textContent.includes('Carte prête');
  22 |     }, { timeout: 15000 });
  23 | 
  24 |     await waitForDiagnosticReady(page);
  25 | 
  26 |     const scoreText = await page.textContent('#global-score');
  27 |     expect(scoreText).toMatch(/\d+/);
  28 | 
  29 |     await page.waitForFunction(() => {
  30 |       const el = document.getElementById('loading');
  31 |       return el && el.style.display === 'none';
  32 |     }, { timeout: 10000 });
  33 |   });
  34 | 
  35 |   test('modal correction change selon type anomalie', async ({ page }) => {
  36 |     await page.goto('/carte', { waitUntil: 'domcontentloaded' });
  37 | 
  38 |     await waitForDiagnosticReady(page);
  39 | 
  40 |     await page.waitForFunction(() => {
  41 |       const select = document.getElementById('select-anomalies-connexions');
  42 |       return !!select && select.options.length > 1;
  43 |     }, { timeout: 10000 });
  44 | 
  45 |     await page.selectOption('#select-anomalies-connexions', { index: 1 });
  46 | 
  47 |     await page.waitForSelector('#correction-modal', { state: 'visible', timeout: 10000 });
  48 | 
  49 |     const formConnexion = await page.isHidden('#form-connexion');
  50 |     expect(formConnexion).toBe(false);
  51 |   });
  52 | });
```