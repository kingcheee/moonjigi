const { chromium } = require('playwright');
(async () => {
  const [base, out, ...rids] = process.argv.slice(2);
  const b = await chromium.launch();
  const errs = [];
  for (const rid of rids) {
    const p = await b.newPage({ viewport: { width: 1600, height: 900 }, deviceScaleFactor: 1 });
    p.on('console', m => { if (m.type() === 'error') errs.push(rid + ': ' + m.text()); });
    p.on('pageerror', e => errs.push(rid + ': ' + e.message));
    await p.goto(`${base}/viewer.html?replay=${rid}&speed=fast`);
    await p.waitForSelector('.end', { timeout: 60000 });
    await p.waitForTimeout(400);
    const h = await p.textContent('#worker-h'); const br = await p.textContent('#brand-sub');
    const pills = await p.$$eval('#stream .res', xs => xs.map(x => x.textContent.trim()));
    const end = await p.textContent('.end');
    console.log(rid, '|', h, '|', br, '|', JSON.stringify(pills), '|', end.replace(/\s+/g, ' '));
    await p.screenshot({ path: `${out}/${rid}.png`, fullPage: true });
    await p.close();
  }
  console.log('errors:', errs.length, errs.slice(0, 5));
  await b.close();
})();
