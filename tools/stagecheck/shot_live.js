const { chromium } = require('playwright');
(async () => {
  const [base, out] = process.argv.slice(2);
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1600, height: 900 }, deviceScaleFactor: 1 });
  const errs = [];
  p.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
  p.on('pageerror', e => errs.push(e.message));
  await p.goto(`${base}/viewer.html`);
  await p.waitForSelector('#scenes .scene');
  const scenes = await p.$$eval('#scenes .scene', xs => xs.map(x => x.dataset.scene));
  console.log('scenes', scenes);
  await p.check('#rule-pii');
  const t0 = Date.now();
  await p.keyboard.press(String(scenes.indexOf('refund-reply') + 1));
  await p.waitForSelector('#confirmbox.on', { timeout: 150000 });
  console.log('confirm shown after', (Date.now() - t0) / 1000, 's ·', (await p.textContent('#confirmbox .msg')).trim());
  await p.waitForTimeout(500);
  await p.screenshot({ path: `${out}/live-confirm.png` });
  // 429: 이 판이 사람 확인을 기다리는 동안 두 판을 더 띄운다
  const r429 = await p.evaluate(async () => {
    const post = (path, body) => fetch(path, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) });
    const a = await post('/worker/run', { scene: 'refund-reply', rules: ['pii'] });
    const aj = await a.json();
    const c = await post('/worker/run', { scene: 'file-move' });
    return { second: a.status, secondRun: aj.run_id, third: c.status, thirdBody: await c.text() };
  });
  console.log('429 test', JSON.stringify(r429));
  await p.keyboard.press('n');
  await p.waitForSelector('.end', { timeout: 60000 });
  await p.waitForTimeout(400);
  console.log('end:', (await p.textContent('.end')).replace(/\s+/g, ' '), '| pills', JSON.stringify(await p.$$eval('#stream .res', xs => xs.map(x => x.textContent.trim()))));
  await p.screenshot({ path: `${out}/live-end.png` });
  // 두 번째 판은 사람 확인이 오면 거절해 끝낸다
  if (r429.secondRun) {
    const res = await p.evaluate(async rid => {
      for (let i = 0; i < 120; i++) {
        const d = await (await fetch(`/worker/events?run=${rid}&since=0`)).json();
        if (d.waiting) { await fetch('/worker/confirm', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ run: rid, approve: false }) }); }
        if (d.done) return d.events[d.events.length - 1];
        await new Promise(r => setTimeout(r, 1000));
      }
      return 'not done';
    }, r429.secondRun);
    console.log('second run end:', JSON.stringify(res).slice(0, 200));
  }
  console.log('errors:', errs.length, errs.slice(0, 5));
  await b.close();
})();
