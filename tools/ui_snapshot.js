#!/usr/bin/env node
// 디자인 묶음 — 공개 데모 화면을 걸음마다 「끝난 상태」로 돌려 놓고 그 DOM을 스크립트 없는 HTML로 떠서,
// 서버 없이 더블클릭으로 열리고 shared.css(:root 토큰)만 고치면 생김새가 바뀌는 폴더를 만든다.
//
//   NODE_PATH=<playwright가 있는 node_modules> node tools/ui_snapshot.js --out <폴더> [--base http://211.233.192.32:8899] [--no-live] [--shots-only]
//   --only a.html,b.html : 그 상태만 다시 뜬다(나머지 파일은 그대로 · 스크린샷은 전부 다시)
//   --shots-only : 이미 뜬 폴더에서 스크린샷만 다시 찍는다(shared.css를 바꾼 뒤 확인할 때 — 서버를 안 쓴다)
//
// 실제 실행 두 번(① 파일 옮기기 · ④ 규칙 켠 답장 → 사람 확인 화면을 뜬 뒤 거절)과 직접 넣어 보기 묻기 한 번을 쓴다. --no-live면 저장된 판으로.
// 결과: <out>/demo-1.html … demo-5.html · try.html · console.html(있으면) · shared.css · console.css · shots/<이름>-{wide,phone}.png
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const arg = (k, d) => { const i = process.argv.indexOf('--' + k); return i > 0 ? process.argv[i + 1] : d; };
const BASE = arg('base', 'http://211.233.192.32:8899').replace(/\/$/, '');
const OUT = path.resolve(arg('out', 'moonjigi-ui'));
const LIVE = !process.argv.includes('--no-live');
const SHOTS_ONLY = process.argv.includes('--shots-only');
const ONLY = arg('only', '') ? arg('only', '').split(',') : null;
const sleep = ms => new Promise(r => setTimeout(r, ms));

const LINKS = { 'index.html': 'demo-1.html', 'try.html': 'try.html', 'console.html': 'console.html' };

const STATES = [
  { file: 'demo-1.html', title: '① 평소 일 — 통과', url: '/index.html#1', go: async p => { await p.keyboard.press('Space'); await p.waitForSelector('.after', { timeout: 30000 }); } },
  { file: 'demo-2.html', title: '② 실수 — 차단 27건', url: '/index.html#2', go: async p => { await p.keyboard.press('Space'); await sleep(800); await p.keyboard.press('e'); await p.waitForSelector('.after', { timeout: 30000 }); } },
  { file: 'demo-3.html', title: '③ 속음 — 차단 + 「문지기가 본 것」 펼침', url: '/index.html#3', go: async p => { await p.keyboard.press('Space'); await p.waitForSelector('.after', { timeout: 30000 }); await p.keyboard.press('d'); await sleep(400); } },
  { file: 'demo-4.html', title: '④ 규칙 밖 — 사람 확인(허락/거절 대기)', url: '/index.html#4', live: true, go: async p => {
    await p.keyboard.press('Space'); await sleep(800); await p.keyboard.press('e'); await p.waitForSelector('.after', { timeout: 30000 });
    await p.keyboard.press('Space'); await p.waitForSelector('[data-answer="no"]', { timeout: 90000 }); await sleep(600);
  }, after: async p => { await p.keyboard.press('n'); await p.waitForFunction(() => document.querySelectorAll('.after').length >= 2, null, { timeout: 30000 }).catch(() => {}); } },
  { file: 'demo-5.html', title: '⑤ 다른 에이전트 — 보류', url: '/index.html#5', go: async p => { await p.keyboard.press('Space'); await sleep(800); await p.keyboard.press('e'); await p.waitForSelector('.after', { timeout: 30000 }); } },
  { file: 'try.html', title: '직접 넣어 보기 — 속음 예시를 물은 뒤', url: '/try.html', go: async p => { await p.click('[data-preset="hidden"]'); await p.click('#ask'); await p.waitForFunction(() => { const r = document.querySelector('.ruling'); return r && !/확인 중/.test(r.innerText); }, null, { timeout: 30000 }); } },
  { file: 'console.html', title: '콘솔 — 승인 대기 · 검문 기록 · 규칙 · 연결', url: '/console.html', optional: true, go: async p => { await sleep(4000); } },
];

function strip(html) {
  let h = html.replace(/<script\b[\s\S]*?<\/script>/gi, '');
  for (const [from, to] of Object.entries(LINKS)) h = h.split(`href="${from}"`).join(`href="${to}"`);
  return h.replace(/<head>/i, '<head>\n<!-- 스냅숏: 공개 데모 화면을 끝난 상태로 떠서 스크립트를 뗀 것. 단추는 움직이지 않는다. 생김새는 shared.css 맨 위 :root 값으로 바뀐다 -->');
}

(async () => {
  fs.mkdirSync(path.join(OUT, 'shots'), { recursive: true });
  const browser = await chromium.launch();
  let made = [];
  if (SHOTS_ONLY) made = JSON.parse(fs.readFileSync(path.join(OUT, 'states.json'), 'utf8'));
  else {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1, locale: 'ko-KR' });
  if (!LIVE) await ctx.route('**/worker/run', r => r.fulfill({ status: 429, body: '{"error":"busy"}', contentType: 'application/json' }));
  for (const css of ['shared.css', 'console.css']) {
    const r = await ctx.request.get(BASE + '/' + css);
    if (r.ok()) fs.writeFileSync(path.join(OUT, css), await r.body());
  }
  for (const s of STATES.filter(s => !ONLY || ONLY.includes(s.file))) {
    const page = await ctx.newPage();
    const resp = await page.goto(BASE + s.url, { waitUntil: 'networkidle' });
    if (!resp || !resp.ok()) { console.log(`건너뜀 ${s.file} — ${resp ? resp.status() : '응답 없음'}`); await page.close(); if (!s.optional) process.exitCode = 1; continue; }
    await sleep(500);
    try { await s.go(page); } catch (e) { console.log(`⚠ ${s.file} 상태 만들기 실패: ${String(e).split('\n')[0]}`); process.exitCode = 1; }
    fs.writeFileSync(path.join(OUT, s.file), strip(await page.content()));
    if (s.after) await s.after(page);
    await page.close();
    made.push(s);
    console.log(`떴다 ${s.file} — ${s.title}`);
  }
  await ctx.close();
  }
  // 뜬 파일을 그대로 열어(서버 없이) 두 폭으로 찍는다 — 묶음이 실제로 그렇게 보인다는 확인을 겸한다
  for (const [w, h, tag] of [[1440, 900, 'wide'], [400, 800, 'phone']]) {
    const c = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: tag === 'phone' ? 2 : 1 });
    for (const s of made) {
      const p = await c.newPage();
      await p.goto('file://' + path.join(OUT, s.file));
      await p.waitForTimeout(200);
      if (!s.file.startsWith('console')) await p.evaluate(() => {   // 걸음 화면은 끝(결정 띠 · 끝난 뒤)이 보이게 내린다. 파일을 열면 맨 위부터 보인다
        for (const el of document.querySelectorAll('*')) { const cs = getComputedStyle(el); if (/(auto|scroll)/.test(cs.overflowY) && el.scrollHeight > el.clientHeight + 4 && !el.closest('.inside')) el.scrollTop = el.scrollHeight; }
        window.scrollTo(0, document.documentElement.scrollHeight);
      });
      await p.waitForTimeout(100);
      const over = await p.evaluate(() => document.documentElement.scrollWidth - innerWidth);
      await p.screenshot({ path: path.join(OUT, 'shots', `${s.file.replace('.html', '')}-${tag}.png`) });
      if (over > 0) console.log(`⚠ ${s.file} ${tag} 가로 넘침 ${over}px`);
      await p.close();
    }
    await c.close();
  }
  await browser.close();
  if (ONLY && fs.existsSync(path.join(OUT, 'states.json'))) {    // 다시 뜬 것만 바꾸고 나머지 목록은 남긴다
    const old = JSON.parse(fs.readFileSync(path.join(OUT, 'states.json'), 'utf8')).filter(o => !made.some(m => m.file === o.file));
    made = STATES.filter(s => old.some(o => o.file === s.file) || made.some(m => m.file === s.file));
  }
  if (!SHOTS_ONLY) fs.writeFileSync(path.join(OUT, 'states.json'), JSON.stringify(made.map(s => ({ file: s.file, title: s.title })), null, 1));
  console.log(`끝 — ${OUT}`);
})();
