// 무대 통 검사: 탭 A(라이브 ①) → B(B1 재생) → C(A2 재생) → D(규칙 끈 판 재생 → 규칙 켬 → 라이브 ④b → N)
const { chromium } = require('playwright');
(async () => {
  const [base, out, norule] = process.argv.slice(2);
  const b = await chromium.launch(); const ctx = await b.newContext({ viewport: { width: 1600, height: 900 } });
  const errs = []; const T = {}; const t0 = Date.now();
  const tab = async (q) => { const p = await ctx.newPage(); p.on('pageerror', e => errs.push(e.message)); p.on('console', m => { if (m.type() === 'error') errs.push(m.text()); }); await p.goto(`${base}/viewer.html${q}`); return p; };
  const A = await tab(''); await A.waitForSelector('#scenes .scene');
  const B = await tab('?replay=replay-B1-delete-spree&speed=fast&hold=1');
  const C = await tab('?replay=replay-A2-wipe&speed=fast&hold=1');
  const D = await tab(`?replay=${norule}&speed=fast&hold=1`);
  await D.waitForTimeout(1500);
  const scenes = await A.$$eval('#scenes .scene', xs => xs.map(x => x.dataset.scene));
  const key = s => String(scenes.indexOf(s) + 1);
  const step = async (name, fn) => { const s = Date.now(); await fn(); T[name] = (Date.now() - s) / 1000; };
  // ① 라이브 셋 — 끝나면 다음 키
  await A.bringToFront();
  for (const sc of ['file-move', 'meeting', 'inbox-summary']) {
    await step('①' + sc, async () => {
      const rid0 = await A.evaluate(() => S && S.rid);
      await A.keyboard.press(key(sc));
      await A.waitForFunction(r0 => S && S.rid !== r0 && S.end, rid0, { timeout: 60000 });
    });
    console.log(sc, '→', (await A.textContent('.end')).replace(/\s+/g, ' '), '| decisions', JSON.stringify(await A.$$eval('#stream .call .pill', xs => xs.map(x => x.textContent))));
  }
  await A.screenshot({ path: `${out}/s1.png` });
  await B.bringToFront(); await step('②B1', async () => { await B.keyboard.press(' '); await B.waitForSelector('.end', { timeout: 60000 }); });
  console.log('B1 →', (await B.textContent('.end')).replace(/\s+/g, ' '));
  await B.screenshot({ path: `${out}/s2.png` });
  await C.bringToFront(); await step('③A2', async () => { await C.keyboard.press('Enter'); await C.waitForSelector('.end', { timeout: 60000 }); });
  await C.waitForTimeout(300); await C.screenshot({ path: `${out}/s3.png` });
  await D.bringToFront(); await step('④a 규칙 끈 판 재생', async () => { await D.keyboard.press(' '); await D.waitForSelector('.end', { timeout: 60000 }); });
  await D.waitForTimeout(300); await D.screenshot({ path: `${out}/s4a.png` });
  await step('④b 규칙 켬 → 사람 확인', async () => { await D.click('#rule-pii'); await D.keyboard.press(key('refund-reply')); await D.waitForSelector('#confirmbox.on', { timeout: 150000 }); });
  console.log('④b msg:', (await D.textContent('#confirmbox .msg')).trim());
  await D.waitForTimeout(300); await D.screenshot({ path: `${out}/s4b.png` });
  await step('④b N → 끝', async () => { await D.keyboard.press('n'); await D.waitForSelector('.end', { timeout: 60000 }); });
  console.log('④b →', (await D.textContent('.end')).replace(/\s+/g, ' '));
  await D.screenshot({ path: `${out}/s4c.png` });
  console.log('times(s)', JSON.stringify(T), 'machine total', Object.values(T).reduce((a, x) => a + x, 0).toFixed(1));
  console.log('errors', errs.length, errs.slice(0, 5));
  await b.close();
})();
