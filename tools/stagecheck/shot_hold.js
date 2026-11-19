const { chromium } = require('playwright');
(async () => {
  const [base, out] = process.argv.slice(2);
  const b = await chromium.launch(); const errs = [];
  const p = await b.newPage({ viewport: { width: 1600, height: 900 } });
  p.on('pageerror', e => errs.push(e.message)); p.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
  await p.goto(`${base}/viewer.html?replay=replay-B1-delete-spree&speed=fast&hold=1`);
  await p.waitForTimeout(3000);
  console.log('before:', (await p.textContent('#stream')).trim().slice(0, 120), '| calls', (await p.$$('#stream .call')).length);
  await p.screenshot({ path: `${out}/hold-before.png` });
  const t0 = Date.now(); await p.keyboard.press(' ');
  await p.waitForSelector('.end', { timeout: 60000 });
  console.log('after: end in', (Date.now() - t0) / 1000, 's · calls', (await p.$$('#stream .call')).length);
  console.log('errors', errs);
  await b.close();
})();
