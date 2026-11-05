import { test, expect } from '@playwright/test';

test('Verify clean contiguous basin without disconnected orphan islands', async ({ page }) => {
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

  // Dismiss modal if present
  const modalVisible = await page.evaluate(() => {
    const m = document.getElementById('modal-project');
    return m && m.style.display !== 'none';
  });
  if (modalVisible) {
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
    }
  }

  // Wait for #bassin-select to have options
  await page.waitForFunction(() => {
    const sel = document.getElementById('bassin-select') as HTMLSelectElement | null;
    return sel && sel.options.length > 5;
  }, { timeout: 45000 });

  // Select Cluster 63
  console.log('Selecting Cluster 63...');
  await page.selectOption('#bassin-select', '63');
  await page.waitForTimeout(2000);

  // Check info box
  const infoText = await page.evaluate(() => {
    const info = document.getElementById('bassin-info');
    return info ? info.innerText : '';
  });
  console.log('Cluster 63 Info Box:\n', infoText);

  expect(infoText).toContain('Regards : 1');
  expect(infoText).not.toContain('orphelins rattachés');
  expect(infoText).toContain('Conduites : 1');

  // Verify map state and zoom
  const mapState = await page.evaluate(() => {
    const win = window as any;
    if (!win.carte) return null;
    return {
      zoom: win.carte.getZoom(),
      center: win.carte.getCenter()
    };
  });
  console.log('Map State on Cluster 63:', mapState);
  expect(mapState?.zoom).toBeGreaterThanOrEqual(15);

  // Screenshot for proof
  const screenshotPath = 'C:/Users/Hakim/.gemini/antigravity/brain/1a90cd7c-1c19-4094-9e1b-2ed2a9315109/test_decoupage_sans_orphelins.png';
  await page.screenshot({ path: screenshotPath, fullPage: false });
  console.log(`Screenshot saved to ${screenshotPath}`);
});
