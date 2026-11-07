import { test, expect } from '@playwright/test';

test('Test E2E Phase 3 : Variantes Techniques d\'Aménagement & Comparatif Financier Multi-Critères', async ({ page }) => {
  test.setTimeout(240000);

  const token = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiNGEwNDcyMC05YzQ5LTQyNjctYWQ3Yy1mODM3ZTBiODM3MTEiLCJlbWFpbCI6ImtlbGxvdWNoZWFlaEBnbWFpbC5jb20iLCJvcmdfaWQiOiJhNjZlMzJhZC1mMzJiLTQ1MjktYWNjMy03YTYwMjZlYjVhOGEiLCJyb2xlIjoib3duZXIiLCJleHAiOjE3OTQ0MzIxNjksImlhdCI6MTc5MzgyNzM2OSwidHlwZSI6ImFjY2VzcyJ9.pt2S4Wfyjg-HH0ntCczdLs9FBtEtEMVd54f4eiMwMEA';

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

  // Fermer la modale projet si présente
  await page.evaluate(() => {
    const win = window as any;
    if (typeof win.montrerModalProjet === 'function') win.montrerModalProjet(false);
    if (typeof win.chargerDonneesInitiales === 'function') win.chargerDonneesInitiales();
  });
  await page.waitForTimeout(2000);

  // S'assurer que le partitionnement des bassins est actif
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

  // Sélectionner le bassin Cité 80 Logts (cluster 87)
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
  console.log('Bassin sélectionné pour test Phase 3 :', targetClusterId);
  expect(targetClusterId).not.toBeNull();

  // Ouvrir la modale de simulation
  await page.evaluate(() => {
    const win = window as any;
    if (typeof win.ouvrirModalSimulation === 'function') {
      win.ouvrirModalSimulation();
    }
    const m = document.getElementById('modal-simulation');
    if (m) m.style.display = 'flex';
  });
  await page.waitForTimeout(1000);

  await page.locator('#sim-select-bassin').selectOption(targetClusterId!);
  await page.waitForTimeout(500);

  // Lancer la simulation SWMM
  console.log('Exécution de la simulation hydrodynamique Saint-Venant...');
  await page.locator('#btn-run-sim-action').click();

  const resultsCard = page.locator('#sim-results-card');
  await expect(resultsCard).toBeVisible({ timeout: 140000 });
  await page.waitForTimeout(2000);

  // 1. VÉRIFIER L'HARMONISATION DE LA SURFACE DANS LE PANNEAU LATÉRAL (117.83 ha) ET CONDUITES (709)
  const lateralText = await page.locator('#bassin-info').innerText();
  console.log('Panneau latéral :', lateralText);
  expect(lateralText).toContain('117.83 ha');
  expect(lateralText).toContain('709');

  // 2. OUVRIR LA MODALE D'INTERPRÉTATION EXPERTE MULTI-AGENTS
  await page.evaluate(() => {
    const win = window as any;
    if (typeof win.ouvrirModalInterpretation === 'function') {
      win.ouvrirModalInterpretation();
    }
  });
  await page.waitForTimeout(1000);

  // 3. VÉRIFIER LA PRÉSENCE ET LE BASCULEMENT SUR L'ONGLET 5 : VARIANTES & FINANCE
  const tabFinanceBtn = page.locator('#btn-tab-agent-finance');
  await expect(tabFinanceBtn).toBeVisible();
  await tabFinanceBtn.click();
  await page.waitForTimeout(600);

  const paneFinance = page.locator('#pane-agent-finance');
  await expect(paneFinance).toBeVisible();

  const financeText = await paneFinance.innerText();
  console.log('Contenu Onglet Finance & Variantes :\n', financeText);

  // Vérifier les 3 variantes
  expect(financeText).toContain('V1 : 100% Tout-Réseau');
  expect(financeText).toContain('330 964 500 DZD');
  expect(financeText).toContain('V2 : 100% SFN Pures');
  expect(financeText).toContain('112 500 000 DZD');
  expect(financeText).toContain('V3 : Mixte Optimisée');
  expect(financeText).toContain('240 384 400 DZD');

  // Vérifier l'économie nette
  expect(financeText).toContain('90.58 M DZD');
  expect(financeText).toContain('-27.4%');

  // Vérifier les ratios directeurs
  const cleanFinanceText = financeText.replace(/[\u202F\u00A0]/g, ' ');
  expect(cleanFinanceText).toContain('47 871 DZD / ml');
  expect(cleanFinanceText).toContain('16 026 DZD / hab');
  expect(cleanFinanceText).toContain('45.0 M DZD / an');
  expect(cleanFinanceText).toContain('5.3 ans');
  expect(cleanFinanceText).toContain('14.8%');
  expect(cleanFinanceText).toContain('+275.8 M DZD');

  // 4. VÉRIFIER L'INTÉGRATION DANS LE RAPPORT COMPLET D'EXPERTISE (imprimerDiagnosticTechniqueComplet)
  const reportHtml = await page.evaluate(() => {
    const win = window as any;
    let generated = '';
    const origOpen = window.open;
    window.open = (() => {
      return {
        document: {
          open: () => {},
          write: (str: string) => { generated += str; },
          close: () => {}
        },
        focus: () => {},
        print: () => {}
      } as any;
    }) as any;

    if (typeof win.imprimerDiagnosticTechniqueComplet === 'function') {
      win.imprimerDiagnosticTechniqueComplet();
    }
    window.open = origOpen;
    return generated;
  });

  const cleanReport = reportHtml.replace(/[\u202F\u00A0]/g, ' ');
  expect(cleanReport).toContain('5. Analyse Multi-Critères des Variantes d\'Aménagement &amp; Décision d\'Investissement (Agent 5)');
  expect(cleanReport).toContain('Variante 1 : 100% Tout-Réseau');
  expect(cleanReport).toContain('330 964 500 DZD');
  expect(cleanReport).toContain('Variante 2 : 100% Solutions Fondées sur la Nature');
  expect(cleanReport).toContain('112 500 000 DZD');
  expect(cleanReport).toContain('Variante 3 : Mixte Optimisée');
  expect(cleanReport).toContain('240 384 400 DZD');
  expect(cleanReport).toContain('90 580 100 DZD');
  expect(cleanReport).toContain('47 871 DZD / ml');
  expect(cleanReport).toContain('16 026 DZD / hab');
  expect(cleanReport).toContain('45 000 000 DZD / an');
  expect(cleanReport).toContain('5.3 ans');
  expect(cleanReport).toContain('14.8%');
  expect(cleanReport).toContain('+275.8 M DZD');

  console.log('✅ Phase 3 validée : Variantes techniques d\'aménagement, comparatif multi-critères et ratios financiers opérationnels.');
});
