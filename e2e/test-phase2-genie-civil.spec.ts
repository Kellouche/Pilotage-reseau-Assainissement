import { test, expect } from '@playwright/test';

test('Test E2E Phase 2 : Génie Civil, Métrés par DN, Règles Fascicule 70 et BPU', async ({ page }) => {
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

  await page.locator('#sim-select-bassin').selectOption(targetClusterId!);
  await page.waitForTimeout(500);

  console.log('Lancement de la simulation SWMM...');
  await page.locator('#btn-run-sim-action').click();

  const resultsCard = page.locator('#sim-results-card');
  await expect(resultsCard).toBeVisible({ timeout: 140000 });
  console.log('Simulation SWMM terminée avec succès.');

  // 1. VÉRIFICATION DES STRUCTURES DE DONNÉES GÉNIE CIVIL (AGENT 2)
  const simData = await page.evaluate(() => {
    const win = window as any;
    return win._dernierResultatSimulation;
  });

  expect(simData).toBeDefined();
  const gc = simData.agents_expertise?.prescriptions_genie_civil;
  expect(gc).toBeDefined();

  console.log('--- Indicateurs Génie Civil Agent 2 ---');
  console.log('Conduites à recalibrer :', gc.nb_troncons_a_recalibrer);
  console.log('Conduites épargnées (remous aval) :', gc.nb_troncons_suffisants_remous);
  console.log('Linéaire total (ml) :', gc.metres_lineaires_totaux);
  console.log('Coût total estimé (DZD) :', gc.cout_global_estime_dzd);
  console.log('Synthèse par DN :', gc.recapitulatif_par_dn);
  console.log('Décomposition BPU :', gc.decomposition_bpu);

  expect(gc.nb_troncons_a_recalibrer).toBeGreaterThan(0);
  expect(gc.metres_lineaires_totaux).toBeGreaterThan(0);
  expect(gc.cout_global_estime_dzd).toBeGreaterThan(0);
  expect(Array.isArray(gc.recapitulatif_par_dn)).toBe(true);
  expect(gc.recapitulatif_par_dn.length).toBeGreaterThan(0);
  expect(gc.decomposition_bpu).toBeDefined();
  expect(gc.decomposition_bpu.montant_terrassement_dzd).toBeGreaterThan(0);
  expect(gc.decomposition_bpu.montant_fourniture_dzd).toBeGreaterThan(0);
  expect(gc.prescriptions_structurelles).toBeDefined();

  // 2. VÉRIFICATION DU RAPPORT IMPRIMABLE (HTML GÉNÉRÉ)
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

  // Vérifier la présence des nouveaux blocs génie civil dans le rapport
  expect(reportHtml).toContain('Prescriptions Structurelles de Pose &amp; Justification Matériaux');
  expect(reportHtml).toContain('Fascicule 70');
  expect(reportHtml).toContain('Convoi Bc 30t');
  expect(reportHtml).toContain('Bordereau Récapitulatif des Métrés par Diamètre &amp; Matériau');
  expect(reportHtml).toContain('Décomposition Analytique du Coût des Travaux (BPU)');
  expect(reportHtml).toContain('Terrassement &amp; Blindage (30%)');
  expect(reportHtml).toContain('Fourniture Tuyaux (35%)');
  expect(reportHtml).toContain('Pose &amp; Remblai 95% (20%)');
  expect(reportHtml).toContain('Réfection Chaussée BB (15%)');

  console.log('✅ Tous les critères de la Phase 2 (Génie Civil, BPU et Métrés) sont validés avec succès !');
});

