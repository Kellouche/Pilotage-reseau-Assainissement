import { test, expect } from '@playwright/test';

test('Test E2E Phase 1 : Opposabilité Juridique, Validation Hydrologique et Harmonisation des Surfaces', async ({ page }) => {
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

  // 1. VÉRIFICATION DU TEXTE DE PLUVIOMÉTRIE DANS L'IHM (AUCUN SYMBOLE LATEX BRUT)
  const pluvioNote = await page.locator('#sim-pluvio-note-text').innerText();
  console.log('Texte note pluviométrique IHM :', pluvioNote);
  expect(pluvioNote).not.toContain('$');
  expect(pluvioNote).not.toContain('\\cdot');
  expect(pluvioNote).not.toContain('\\text');
  expect(pluvioNote).toContain('Formule Montana I(t) = 9.334');

  // Fermer la modale projet si affichée
  await page.evaluate(() => {
    const win = window as any;
    if (typeof win.montrerModalProjet === 'function') win.montrerModalProjet(false);
    if (typeof win.chargerDonneesInitiales === 'function') win.chargerDonneesInitiales();
  });
  await page.waitForTimeout(2500);

  // S'assurer que les bassins sont chargés
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

  // Sélectionner Cite 80 Logts (Cluster 87)
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

  // Ouvrir la modale de simulation et lancer le calcul
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

  // Attendre le résultat de simulation
  const resultsCard = page.locator('#sim-results-card');
  await expect(resultsCard).toBeVisible({ timeout: 140000 });
  console.log('Simulation SWMM terminée avec succès.');

  // 2. VÉRIFIER LES DONNÉES EN MÉMOIRE
  const simData = await page.evaluate(() => {
    const win = window as any;
    return win._dernierResultatSimulation;
  });

  expect(simData).toBeDefined();
  const meta = simData.meta || {};
  const agents = simData.agents_expertise || {};
  const bufferCurve = (simData.buffer_sensitivity && simData.buffer_sensitivity.curve) || [];

  console.log('Surface drainée simulée (ha) :', meta.total_area_ha);
  console.log('Buffer 35m dans la courbe de sensibilité :', bufferCurve.find((c: any) => Math.round(c.buffer_m) === 35));

  // Vérifier la cohérence de la surface du Buffer 35m (117.83 ha)
  const buf35 = bufferCurve.find((c: any) => Math.round(c.buffer_m) === 35);
  expect(buf35).toBeDefined();
  expect(buf35.surface_ha).toBeCloseTo(meta.total_area_ha, 1);

  // 3. VÉRIFIER LA FORMULATION JURIDIQUE PRUDENTE DANS LES AGENTS
  const recCle = agents.synthese_executive?.recommandation_cle || '';
  console.log('Recommandation clé Agent 5 :', recCle);
  expect(recCle).not.toContain('éliminera 100%');
  expect(recCle).toContain('résorption théorique intégrale');

  // 4. TESTER LE RAPPORT D'EXPERTISE (HTML GÉNÉRÉ POUR L'IMPRESSION)
  const reportHtml = await page.evaluate(() => {
    const win = window as any;
    let generated = '';
    // Mock window.open pour capturer le document généré
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

  expect(reportHtml).toContain('Rapport d\'Expertise Hydraulique');
  expect(reportHtml).toContain('Cadre de Validation Hydrologique &amp; Modèle d\'Infiltration');
  expect(reportHtml).toContain('Horton Exponentiel');
  expect(reportHtml).toContain('C_imp = 65%');
  expect(reportHtml).toContain('Station ANRH Chlef Siège');
  expect(reportHtml).toContain('117.83 ha');
  expect(reportHtml).not.toContain('éliminera 100%');

  console.log('✅ Tous les critères de la Phase 1 sont validés avec succès !');
});
