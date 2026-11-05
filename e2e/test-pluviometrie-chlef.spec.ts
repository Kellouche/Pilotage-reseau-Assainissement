import { test, expect } from '@playwright/test';

test('Test E2E Pluviométrie Chlef : Stations ANRH, Formule Montana et Simulation', async ({ page }) => {
  test.setTimeout(90000);

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
  await page.waitForTimeout(2500);

  // Fermer la modale projet si affichée
  await page.evaluate(() => {
    const win = window as any;
    if (typeof win.montrerModalProjet === 'function') win.montrerModalProjet(false);
    if (typeof win.chargerDonneesInitiales === 'function') win.chargerDonneesInitiales();
  });
  await page.waitForTimeout(2000);

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

  // 1. Ouvrir la modale de simulation
  await page.evaluate(() => {
    const win = window as any;
    if (typeof win.ouvrirModalSimulation === 'function') {
      win.ouvrirModalSimulation();
    }
    const m = document.getElementById('modal-simulation');
    if (m) m.style.display = 'flex';
  });
  await page.waitForTimeout(1000);

  // 2. Vérifier la présence du sélecteur de stations ANRH
  const stationSelect = page.locator('#sim-select-station');
  await expect(stationSelect).toBeVisible();

  // Vérifier la présence des 7 stations de la Wilaya de Chlef
  const options = await stationSelect.locator('option').allInnerTexts();
  console.log('Stations disponibles dans le sélecteur :', options);

  const optionsValues = await stationSelect.locator('option').evaluateAll((opts: HTMLOptionElement[]) => opts.map(o => o.value));
  expect(optionsValues).toContain('chlef_anrh_siege');
  expect(optionsValues).toContain('chlef_ponteba_oum_drou');
  expect(optionsValues).toContain('chlef_oued_fodda');
  expect(optionsValues).toContain('chlef_benairia_dahra');
  expect(optionsValues).toContain('chlef_domaine_si_tayeb');
  expect(optionsValues).toContain('chlef_tenes_littoral');
  expect(optionsValues).toContain('chlef_boukadir');

  // 3. Vérifier les paramètres de la station par défaut (Chlef Siège)
  const imaxInput = page.locator('#sim-input-intensite-max');
  await expect(imaxInput).toHaveValue('74.9');

  const noteText = await page.locator('#sim-pluvio-note-text').innerText();
  console.log('Note pluviométrique Chlef Siège :', noteText);
  expect(noteText).toContain('Chlef Siège');
  expect(noteText).toContain('9.334');
  expect(noteText).toContain('0.745');

  // 4. Tester le basculement dynamique vers une autre station (Oued Fodda)
  await stationSelect.selectOption('chlef_oued_fodda');
  await page.waitForTimeout(1500);

  const imaxOuedFodda = await imaxInput.inputValue();
  console.log('Intensité décennale Oued Fodda :', imaxOuedFodda);
  expect(parseFloat(imaxOuedFodda)).toBeCloseTo(78.5, 0.5);

  const noteOuedFodda = await page.locator('#sim-pluvio-note-text').innerText();
  console.log('Note Oued Fodda :', noteOuedFodda);
  expect(noteOuedFodda).toContain('Oued Fodda');

  // 5. Tester la saisie manuelle personnalisée (ex: 85 mm/h)
  await imaxInput.fill('85.0');
  await page.evaluate(() => {
    const inp = document.getElementById('sim-input-intensite-max') as HTMLInputElement;
    const win = window as any;
    if (inp && typeof win.onChangementIntensitePluie === 'function') {
      win.onChangementIntensitePluie('85.0');
    }
  });
  await page.waitForTimeout(500);

  const scenarioSel = page.locator('#sim-select-scenario');
  await expect(scenarioSel).toHaveValue('personnalise');

  // 6. Revenir à Chlef Siège Décennale Réglementaire et lancer une simulation
  await stationSelect.selectOption('chlef_anrh_siege');
  await page.waitForTimeout(1000);
  await scenarioSel.selectOption('pluie_decennale');
  await page.waitForTimeout(500);

  // Sélectionner un bassin si disponible
  const basinOptions = await page.locator('#sim-select-bassin option').evaluateAll((opts: HTMLOptionElement[]) => opts.map(o => o.value));
  console.log('Bassins disponibles pour la simulation :', basinOptions);
  if (basinOptions.length > 0) {
    const validBassin = basinOptions.find(b => b && b !== '') || basinOptions[0];
    await page.locator('#sim-select-bassin').selectOption(validBassin);
    await page.waitForTimeout(500);

    // Déclencher la simulation
    console.log('Déclenchement de la simulation SWMM...');
    const btnSim = page.locator('#btn-run-sim-action');
    await btnSim.click();

    // Attendre l'affichage des résultats (au maximum 45s)
    const resultsCard = page.locator('#sim-results-card');
    await expect(resultsCard).toBeVisible({ timeout: 45000 });

    // Vérifier les indicateurs hydro-météo dans le résultat
    const resStationBadge = await page.locator('#kpi-pluvio-station-badge').innerText();
    const resImax = await page.locator('#kpi-pluvio-imax').innerText();
    const resMontana = await page.locator('#kpi-pluvio-montana').innerText();

    console.log('Résultats simulation hydro-météo :', {
      station: resStationBadge,
      imax: resImax,
      montana: resMontana
    });

    expect(resStationBadge).toContain('Chlef Siège');
    expect(resImax).toContain('74.9');
    expect(resMontana).toContain('9.334');
  }

  console.log('✅ Test E2E Pluviométrie Chlef exécuté avec succès.');
});

