import { test, expect } from '@playwright/test';

test('Test zoom on bassin selection in side panel', async ({ page }) => {
  test.setTimeout(90000);

  const token = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiNGEwNDcyMC05YzQ5LTQyNjctYWQ3Yy1mODM3ZTBiODM3MTEiLCJlbWFpbCI6ImtlbGxvdWNoZWFlaEBnbWFpbC5jb20iLCJvcmdfaWQiOiJhNjZlMzJhZC1mMzJiLTQ1MjktYWNjMy03YTYwMjZlYjVhOGEiLCJyb2xlIjoib3duZXIiLCJleHAiOjE3OTQ0MzIxNjksImlhdCI6MTc5MzgyNzM2OSwidHlwZSI6ImFjY2VzcyJ9.pt2S4Wfyjg-HH0ntCczdLs9FBtEtEMVd54f4eiMwMEA';

  // Set cookies
  await page.context().addCookies([
    {
      name: 'access_token',
      value: token,
      domain: 'localhost',
      path: '/'
    }
  ]);

  // Navigate to cockpit
  await page.goto('http://localhost:5002/cockpit', { waitUntil: 'domcontentloaded' });

  // Set session and local storage
  await page.evaluate((tok) => {
    sessionStorage.setItem('projet_charge', 'true');
    localStorage.setItem('swmm_access_token', tok);
  }, token);

  // Reload with storage set
  await page.goto('http://localhost:5002/cockpit', { waitUntil: 'networkidle' });
  await page.waitForTimeout(3000);

  // Check if modal-project is visible, if so click "reprendre"
  const modalVisible = await page.evaluate(() => {
    const m = document.getElementById('modal-project');
    return m && m.style.display !== 'none';
  });
  if (modalVisible) {
    console.log('modal-project visible, dismissing...');
    await page.evaluate(() => {
      const win = window as any;
      if (typeof win.montrerModalProjet === 'function') win.montrerModalProjet(false);
      if (typeof win.chargerDonneesInitiales === 'function') win.chargerDonneesInitiales();
    });
    await page.waitForTimeout(3000);
  }

  // Check if #bassin-select exists and has options
  let optionsCount = await page.evaluate(() => {
    const sel = document.getElementById('bassin-select') as HTMLSelectElement | null;
    return sel ? sel.options.length : 0;
  });
  console.log(`Initial #bassin-select options count: ${optionsCount}`);

  // If not partitioned yet, click partition button
  if (optionsCount <= 1) {
    console.log('Clicking #detect-cluster-btn to partition...');
    const btn = page.locator('#detect-cluster-btn');
    if (await btn.isVisible()) {
      await btn.click();
      await page.waitForFunction(() => {
        const sel = document.getElementById('bassin-select') as HTMLSelectElement | null;
        return sel && sel.options.length > 5;
      }, { timeout: 45000 });
    }
  }

  // Log options in #bassin-select
  const options = await page.evaluate(() => {
    const sel = document.getElementById('bassin-select') as HTMLSelectElement;
    const list: { value: string; text: string }[] = [];
    if (!sel) return list;
    for (let i = 0; i < sel.options.length; i++) {
      list.push({ value: sel.options[i].value, text: sel.options[i].text });
    }
    return list;
  });
  console.log(`Loaded ${options.length} options in #bassin-select. First 8:`, options.slice(0, 8));

  // Initial map state
  const initialMapState = await page.evaluate(() => {
    const win = window as any;
    if (!win.carte) return null;
    return {
      zoom: win.carte.getZoom(),
      center: win.carte.getCenter()
    };
  });
  console.log('Initial map state:', initialMapState);

  // Now select a major basin, for example cluster 7 (Guezzous) or 27 (Hay Cherifi)
  const targetOption = options.find(o => o.text.includes('Guezzous') || o.value === '7') || options[1];
  console.log('Selecting option:', targetOption);

  await page.selectOption('#bassin-select', targetOption.value);
  await page.waitForTimeout(2500);

  // Check map state after selection
  const afterMapState = await page.evaluate((targetVal) => {
    const win = window as any;
    if (!win.carte) return null;
    const bBounds = win._bassinBounds ? (win._bassinBounds[targetVal] || win._bassinBounds[String(targetVal)]) : null;
    return {
      zoom: win.carte.getZoom(),
      center: win.carte.getCenter(),
      bounds: win.carte.getBounds(),
      has_bassinBounds: Boolean(win._bassinBounds),
      bBounds_found: Boolean(bBounds),
      bBounds_val: bBounds ? { sw: bBounds.getSouthWest(), ne: bBounds.getNorthEast() } : null
    };
  }, targetOption.value);
  console.log('Map state after selecting', targetOption.text, ':', afterMapState);

  // Now select another basin: Meknassa 41
  const meknassaOpt = options.find(o => o.value === '41' || (o.text.includes('Meknassa') && !o.text.includes('0.38')));
  if (meknassaOpt) {
    console.log('Now selecting Meknassa:', meknassaOpt);
    await page.selectOption('#bassin-select', meknassaOpt.value);
    await page.waitForTimeout(2500);

    const meknassaMapState = await page.evaluate((val) => {
      const win = window as any;
      if (!win.carte) return null;
      const bBounds = win._bassinBounds ? (win._bassinBounds[val] || win._bassinBounds[String(val)]) : null;
      return {
        zoom: win.carte.getZoom(),
        center: win.carte.getCenter(),
        bBounds_found: Boolean(bBounds),
        bBounds_val: bBounds ? { sw: bBounds.getSouthWest(), ne: bBounds.getNorthEast() } : null
      };
    }, meknassaOpt.value);
    console.log('Map state after selecting Meknassa:', meknassaMapState);
  }

  // Take screenshot
  await page.screenshot({ path: 'test-results/zoom-test.png', fullPage: false });
  console.log('Screenshot saved to test-results/zoom-test.png');
});
