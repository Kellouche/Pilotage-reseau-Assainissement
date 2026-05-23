const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  page.on('console', msg => {
    if (msg.type() === 'error') console.log('CONSOLE ERROR:', msg.text());
  });
  page.on('pageerror', err => console.log('PAGE ERROR:', err.message));

  try {
    await page.goto('http://127.0.0.1:5001/carte', { waitUntil: 'domcontentloaded', timeout: 60000 });

    // Click on tab connexions to trigger diagnostic modal and async analysis
    console.log('Clicking tab connexions to start diagnostic...');
    await page.click('#tab-connexions');

    // Wait for diagnostic modal to become visible
    console.log('Waiting for diagnostic modal...');
    await page.waitForSelector('#diagnostic-modal', { state: 'visible', timeout: 5000 });
    
    // Wait for diagnostic modal to become hidden (completion of diagnostic)
    console.log('Waiting for diagnostic to complete...');
    await page.waitForSelector('#diagnostic-modal', { state: 'hidden', timeout: 180000 });
    console.log('Diagnostic completed successfully via UI modal flow!');

    // Wait for anomalies select to be present in DOM
    await page.waitForSelector('#select-anomalies-connexions', { state: 'attached', timeout: 30000 });
    // Wait until options are populated (poll)
    let select = await page.$('#select-anomalies-connexions');
    let options = await select.$$('option');
    const start = Date.now();
    while (options.length <= 1 && (Date.now() - start) < 30000) {
      await page.waitForTimeout(500);
      options = await (await page.$('#select-anomalies-connexions')).$$('option');
    }
    console.log('OPTIONS after wait:', options.length);

    // choose first non-empty option (skip index 0)
    let chosen = null;
    for (let i = 1; i < options.length; i++) {
      const val = await options[i].getAttribute('value');
      if (val && val.trim() !== '') { chosen = val; break; }
    }

    if (!chosen) {
      console.log('No selectable anomaly option found — test ends.');
      await browser.close();
      process.exit(0);
    }

    // accept any confirm dialogs automatically
    page.on('dialog', async dialog => { console.log('DIALOG:', dialog.message()); await dialog.accept(); });

    await select.selectOption(chosen);

    // Wait for modal
    await page.waitForSelector('#correction-modal', { state: 'visible', timeout: 10000 });
    console.log('Modal visible');

    // Click Tracer profil if present
    const tracerBtn = await page.$("button:has-text('Tracer profil')");
    if (tracerBtn) {
      await tracerBtn.click();
      // wait for profile container
      await page.waitForSelector('#profile-container', { state: 'visible', timeout: 5000 });
      const canvas = await page.$('#profile-canvas');
      console.log('Profile canvas present:', !!canvas);
    } else {
      console.log('Tracer profil button not found');
    }

    // If Apply button present and enabled, click it (will confirm if needed)
    const applyBtn = await page.$('#apply-suggestion-btn');
    if (applyBtn) {
      await applyBtn.click();
      console.log('Apply clicked');
      // wait a moment
      await page.waitForTimeout(1000);
    } else {
      console.log('Apply button not present');
    }

    await browser.close();
    console.log('Test finished');
  } catch (e) {
    console.error('TEST ERROR', e);
    await browser.close();
    process.exit(1);
  }
})();
