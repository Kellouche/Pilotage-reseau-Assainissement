# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: map-detect-basins.spec.ts >> detect urban basins button completes without error
- Location: e2e\map-detect-basins.spec.ts:3:5

# Error details

```
Error: expect(received).toContain(expected) // indexOf

Expected substring: "Détection terminée"
Received string:    "Erreur lors de la détection : Failed to fetch"
```

# Page snapshot

```yaml
- generic [active] [ref=e1]:
  - generic [ref=e2]:
    - heading "SWMM Platform" [level=2] [ref=e3]
    - generic [ref=e4]: "Conduites: 10295 | Regards: 10538 | Stations: 5 | STEP: 1 | Ouvrages: 38"
    - generic [ref=e5]:
      - checkbox "Conduites" [checked] [ref=e6]
      - text: Conduites
      - checkbox "Regard" [ref=e7]
      - text: Regard
      - checkbox "Stations" [checked] [ref=e8]
      - text: Stations
      - checkbox "STEP" [checked] [ref=e9]
      - text: STEP
      - checkbox "Ouvrages" [checked] [ref=e10]
      - text: Ouvrages
      - separator [ref=e11]
      - checkbox "Bassins Versants" [disabled] [ref=e12]
      - generic [ref=e13]: Bassins Versants
    - separator [ref=e14]
    - generic [ref=e15]:
      - heading "📡 Modifications récentes 0" [level=3] [ref=e16]:
        - text: 📡 Modifications récentes
        - generic [ref=e17]: "0"
      - generic [ref=e20]: En attente de modifications...
    - text: 
    - button "Détecter les bassins urbains" [ref=e21] [cursor=pointer]
    - generic [ref=e22]: "Erreur lors de la détection : Failed to fetch"
  - generic [ref=e23]:
    - button "" [ref=e24] [cursor=pointer]:
      - generic [ref=e25]: 
    - button "" [disabled] [ref=e26]:
      - generic [ref=e27]: 
    - button "" [disabled] [ref=e28]:
      - generic [ref=e29]: 
    - separator [ref=e30]
    - button "" [disabled] [ref=e31]:
      - generic [ref=e32]: 
  - generic [ref=e33]:
    - generic [ref=e34]:
      - generic:
        - generic:
          - img
      - generic:
        - generic [ref=e79]:
          - button "Zoom in" [ref=e80] [cursor=pointer]: +
          - button "Zoom out" [ref=e81] [cursor=pointer]: −
        - generic [ref=e82]:
          - link "Leaflet" [ref=e83] [cursor=pointer]:
            - /url: https://leafletjs.com
            - img [ref=e84]
            - text: Leaflet
          - text: "| © OpenStreetMap"
    - generic [ref=e88]: "Zoom: 13"
```

# Test source

```ts
  1  | import { test, expect } from '@playwright/test';
  2  | 
  3  | test('detect urban basins button completes without error', async ({ page }) => {
  4  |   test.setTimeout(180000);
  5  |   await page.goto('/map', { waitUntil: 'domcontentloaded' });
  6  | 
  7  |   await page.locator('#detect-cluster-btn').click();
  8  | 
  9  |   await expect(page.locator('#detect-cluster-btn')).toBeEnabled({ timeout: 120000 });
  10 | 
  11 |   await page.waitForFunction(() => {
  12 |     const status = document.getElementById('cluster-status')?.textContent || '';
  13 |     return status.includes('Détection terminée') || status.includes('Erreur lors de la détection') || status.includes('Aucun cluster détecté');
  14 |   }, { timeout: 120000 });
  15 | 
  16 |   const status = await page.locator('#cluster-status').textContent();
> 17 |   expect(status).toContain('Détection terminée');
     |                  ^ Error: expect(received).toContain(expected) // indexOf
  18 |   expect(status).not.toContain('Erreur lors de la détection');
  19 | });
  20 | 
```