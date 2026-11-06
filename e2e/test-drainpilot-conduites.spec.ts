import { test, expect } from '@playwright/test';

test('Test E2E DrainPilot : Vérification Brand SaaS et Cohérence Conduites (709)', async ({ page }) => {
  test.setTimeout(140000);

  const token = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiNGEwNDcyMC05YzQ5LTQyNjctYWQ3Yy1mODM3ZTBiODM3MTEiLCJlbWFpbCI6ImtlbGxvdWNoZWFlaEBnbWFpbC5jb20iLCJvcmdfaWQiOiJhNjZlMzJhZC1mMzJiLTQ1MjktYWNjMy03YTYwMjZlYjVhOGEiLCJyb2xlIjoib3duZXIiLCJleHAiOjE3OTQ0MzIxNjksImlhdCI6MTc5MzgyNzM2OSwidHlwZSI6ImFjY2VzcyJ9.pt2S4Wfyjg-HH0ntCczdLs9FBtEtEMVd54f4eiMwMEA';

  // Configurer cookies et stockage local
  await page.context().addCookies([
    {
      name: 'access_token',
      value: token,
      domain: 'localhost',
      path: '/'
    }
  ]);

  await page.goto('http://localhost:5002/cockpit', { waitUntil: 'domcontentloaded' });

  await page.evaluate((tok) => {
    sessionStorage.setItem('projet_charge', 'true');
    localStorage.setItem('swmm_access_token', tok);
  }, token);

  await page.goto('http://localhost:5002/cockpit', { waitUntil: 'networkidle' });
  await page.waitForTimeout(2000);

  // 1. VÉRIFICATION DU NOM SAAS DRAINPILOT
  const pageTitle = await page.title();
  console.log('Titre de la page :', pageTitle);
  expect(pageTitle).toContain('DrainPilot');

  const brandText = await page.locator('.nav-brand-title').innerText();
  console.log('Marque du bandeau haut :', brandText);
  expect(brandText).toContain('DrainPilot');

  // Fermer la modale projet si affichée
  await page.evaluate(() => {
    const win = window as any;
    if (typeof win.montrerModalProjet === 'function') win.montrerModalProjet(false);
    if (typeof win.chargerDonneesInitiales === 'function') win.chargerDonneesInitiales();
  });
  await page.waitForTimeout(2500);

  // S'assurer que les bassins sont partitionnés
  let optionsCount = await page.evaluate(() => {
    const sel = document.getElementById('bassin-select') as HTMLSelectElement | null;
    return sel ? sel.options.length : 0;
  });
  if (optionsCount <= 1) {
    const btn = page.locator('#detect-cluster-btn');
    if (await btn.isVisible()) {
      await btn.click();
    }
    await page.waitForFunction(() => {
      const sel = document.getElementById('bassin-select') as HTMLSelectElement | null;
      return sel && sel.options.length > 2;
    }, { timeout: 35000 });
  }

  // 2. SÉLECTIONNER LE BASSIN CITE 80 LOGTS (CLUSTER 87)
  const targetClusterId = await page.evaluate(() => {
    const sel = document.getElementById('bassin-select') as HTMLSelectElement | null;
    if (!sel) return null;
    for (const opt of Array.from(sel.options)) {
      if (opt.text.includes('80 Logts') || opt.value === '87') {
        sel.value = opt.value;
        sel.dispatchEvent(new Event('change'));
        return opt.value;
      }
    }
    return null;
  });
  console.log('Bassin sélectionné :', targetClusterId);
  expect(targetClusterId).not.toBeNull();

  await page.waitForTimeout(1000);

  // 3. VÉRIFIER LE COMPTE DANS LE PANNEAU LATÉRAL AVANT SIMULATION
  const lateralTextAvant = await page.locator('#bassin-info').innerText();
  console.log('Panneau latéral AVANT simulation :\n', lateralTextAvant);
  expect(lateralTextAvant).toContain('709');
  expect(lateralTextAvant).not.toContain('702');

  // 4. LANCER LA SIMULATION DU BASSIN 87
  await page.evaluate(() => {
    const win = window as any;
    if (typeof win.ouvrirModalSimulation === 'function') {
      win.ouvrirModalSimulation();
    }
    const m = document.getElementById('modal-simulation');
    if (m) m.style.display = 'flex';
  });
  await page.waitForTimeout(1000);

  // Sélectionner le bassin 87 dans la modale
  await page.locator('#sim-select-bassin').selectOption(targetClusterId!);
  await page.waitForTimeout(500);

  // Déclencher la simulation
  console.log('Lancement de la simulation SWMM...');
  await page.locator('#btn-run-sim-action').click();

  // Attendre l'affichage des résultats
  const resultsCard = page.locator('#sim-results-card');
  await expect(resultsCard).toBeVisible({ timeout: 80000 });

  await page.waitForTimeout(2000);

  // 5. VÉRIFICATION DE LA COHÉRENCE APRÈS SIMULATION
  // A. Panneau latéral
  const lateralTextApres = await page.locator('#bassin-info').innerText();
  console.log('Panneau latéral APRÈS simulation :\n', lateralTextApres);
  expect(lateralTextApres).toContain('709');
  expect(lateralTextApres).not.toContain('702');

  // B. Bandeau supérieur mini-stats
  const miniStatsText = await page.locator('#mini-stats').innerText();
  console.log('Bandeau mini-stats :', miniStatsText);
  expect(miniStatsText).toContain('709');

  // C. Infobulle / Tooltip Leaflet sur la carte
  const tooltipContent = await page.evaluate(() => {
    const el = document.querySelector('.sim-bassin-tooltip');
    return el ? (el as HTMLElement).innerText : '';
  });
  console.log('Contenu infobulle carte :\n', tooltipContent);
  if (tooltipContent) {
    expect(tooltipContent).toContain('709');
    expect(tooltipContent).not.toContain('702');
  }

  console.log('✅ Synchronisation parfaite validée : DrainPilot affiche 709 conduites dans toutes les vues.');
});
