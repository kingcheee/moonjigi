#!/usr/bin/env node
// 시연 영상 녹화 — 공개 데모 화면을 장면마다 키와 DOM 이름으로 몰면서 프레임을 찍어 장면별 mp4를 만든다.
//
//   NODE_PATH=<playwright가 있는 node_modules> node tools/record_demo.js --out <폴더> [--base http://211.233.192.32:8899] [--scenes 1,2,3,4,5]
//
// 화면은 CSS 1536×864에 배율 1.25로 그려 1920×1080 프레임을 얻는다(글자를 키운 채 기기 픽셀 그대로 — recordVideo는 CSS 크기로 찍혀 흐려진다).
// 프레임은 page.screenshot(jpeg) 연속 촬영(약 20장/초)이고, 찍은 시각대로 이어 붙여 30fps H.264로 만든다.
// 글자(문구)는 보지 않는다 — 화면 문구가 바뀌어도 다시 돌리면 되게 키(Space · N · D)와 이름(.after · [data-answer] · #log)만 쓴다.
//
// 결과: <out>/scene-<n>/f*.jpg · <out>/scene-<n>/timeline.json(동작 시각) · <out>/scene-<n>.mp4
// 장면 5는 다른 에이전트(pi + 문지기 MCP)를 실제로 한 판 돌린다 — mcp/run_pi.py · 기록은 <out>/pi-runs/
const { chromium } = require('playwright');
const { spawn, execFileSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const arg = (k, d) => { const i = process.argv.indexOf('--' + k); return i > 0 ? process.argv[i + 1] : d; };
const BASE = arg('base', 'http://211.233.192.32:8899').replace(/\/$/, '');
const OUT = path.resolve(arg('out', 'demo-video'));
const ONLY = arg('scenes', '1,2,3,4,5').split(',').map(Number);
const REPO = path.resolve(__dirname, '..');
const VIEW = { width: 1536, height: 864 }, DSF = 1.25;   // → 1920×1080

const sleep = ms => new Promise(r => setTimeout(r, ms));

// 장면: 길이(초)와 동작. at(s) = 장면 시작에서 s초가 될 때까지 기다림. 길이는 영상 대본 초안의 배분(10 · 20 · 15 · 30 · 25).
const SCENES = {
  1: { name: '평소 일', url: '/index.html#1', dur: 10, run: async ({ page, at, mark }) => {
    await at(1.0); await page.keyboard.press('Space'); mark('시키기 — 파일 옮기기(실제 실행)');
    await page.waitForSelector('.after', { timeout: 8500 }).then(() => mark('끝난 뒤'), () => mark('⚠ 끝나지 않음'));
  } },
  2: { name: '실수', url: '/index.html#2', dur: 20, run: async ({ page, at, mark }) => {
    await at(1.0); await page.keyboard.press('Space'); mark('재생 시작(저장된 기록)');
    await page.waitForSelector('.after', { timeout: 18500 }).then(() => mark('끝난 뒤'), () => mark('⚠ 끝나지 않음'));
  } },
  3: { name: '속음', url: '/index.html#3', dur: 15, run: async ({ page, at, mark }) => {
    await at(1.5); await page.keyboard.press('Space'); mark('재생 시작(저장된 기록)');
    await page.waitForSelector('.after', { timeout: 8000 }).then(() => mark('끝난 뒤'), () => mark('⚠ 끝나지 않음'));
    await at(7.0); await page.keyboard.press('d'); mark('문지기가 본 것 열기');
  } },
  4: { name: '규칙 밖', url: '/index.html#4', dur: 30, run: async ({ page, at, mark }) => {
    await at(1.0); await page.keyboard.press('Space'); mark('규칙 없이 — 재생 시작(저장된 기록)');
    await page.waitForSelector('.after', { timeout: 14000 }).then(() => mark('규칙 없이 — 끝난 뒤'), () => mark('⚠ 4a 끝나지 않음'));
    await at(16.0); await page.keyboard.press('Space'); mark('규칙 켜고 — 시키기(실제 실행)');
    const asked = await page.waitForSelector('[data-answer="no"]', { timeout: 9000 }).then(() => true, () => false);
    mark(asked ? '사람 확인 단추' : '⚠ 사람 확인 단추가 안 뜸');
    if (asked) { await sleep(2500); await page.keyboard.press('n'); mark('거절(N)'); }
    await page.waitForFunction(() => document.querySelectorAll('.after').length >= 2, null, { timeout: 8000 })
      .then(() => mark('규칙 켜고 — 끝난 뒤'), () => mark('⚠ 4b 끝나지 않음'));
  } },
  5: { name: '콘솔', url: '/console.html', dur: 25, run: async ({ page, at, mark }) => {
    const conn = await page.$('#connect');
    if (conn) { await conn.scrollIntoViewIfNeeded(); mark('연결 칸'); }
    await at(3.0);
    const runs = path.join(OUT, 'pi-runs'); fs.mkdirSync(runs, { recursive: true });
    const pi = spawn('python3', ['mcp/run_pi.py', '--scene', 'refund-reply', '--rules', 'pii', '--gate', BASE, '--runs-dir', runs],
      { cwd: REPO, stdio: ['ignore', fs.openSync(path.join(OUT, 'scene-5-pi.out'), 'w'), 'inherit'] });
    mark('다른 에이전트 시작(pi + 문지기 MCP · 실제 실행)');
    let piCode = null;
    pi.on('exit', c => { piCode = c; mark(c === 0 ? '다른 에이전트 끝(종료 코드 0)' : `⚠ 다른 에이전트 종료 코드 ${c}`); });
    const log = await page.$('#log');
    if (log) { await at(4.0); await log.scrollIntoViewIfNeeded(); mark('검문 기록 칸'); }
    // 새 줄이 생길 때만 표시(최대 약 20초). 「최근 연결」은 기다리지 않는다 — pi 판 기록은 노트북에 남아 공개 서버 목록에 안 생긴다
    const count = () => page.$$eval('[data-log-row]', r => r.length).catch(() => 0);
    const confirms = () => page.$$eval('[data-log-row][data-decision="CONFIRM"]', r => r.length).catch(() => 0);
    const before = await count(), c0 = await confirms();
    let last = before;
    for (let k = 0; k < 40; k++) {
      await sleep(500);
      const n = await count();
      if (n !== last) { last = n; mark(`검문 기록 ${n - before}줄 늘어남`); }
      if (await confirms() > c0) { mark('보류 줄(사람 확인) 뜸'); break; }
    }
    if (await confirms() <= c0) mark('⚠ 보류 줄이 안 뜸(무료 호출 한도 · 모델이 안 속음 등 — scene-5-pi.out 확인)');
    await at(24.5);
    if (piCode === null) mark('⚠ 다른 에이전트가 장면 안에 안 끝남');
  } },
};

async function capture(page, dir, state) {
  const frames = [];
  let i = 0;
  while (!state.stop) {
    const a = performance.now();
    const buf = await page.screenshot({ type: 'jpeg', quality: 90 });
    const t = ((a + performance.now()) / 2 - state.t0) / 1000;
    const name = `f${String(i++).padStart(5, '0')}.jpg`;
    fs.writeFileSync(path.join(dir, name), buf);
    frames.push([name, Math.max(0, t)]);
  }
  return frames;
}

function encode(dir, frames, dur, mp4) {
  // 찍은 시각대로 이어 붙인다(가변 간격) → 30fps로 고정 · 길이는 정확히 dur초
  const lines = ['ffconcat version 1.0'];
  frames.forEach(([name, t], k) => {
    const next = k + 1 < frames.length ? frames[k + 1][1] : dur;
    lines.push(`file '${name}'`, `duration ${Math.max(0.001, next - (k === 0 ? 0 : t)).toFixed(4)}`);
  });
  lines.push(`file '${frames[frames.length - 1][0]}'`);   // 마지막 장은 한 번 더 적어야 duration이 먹는다
  fs.writeFileSync(path.join(dir, 'frames.ffconcat'), lines.join('\n') + '\n');
  execFileSync('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', path.join(dir, 'frames.ffconcat'),
    '-vf', `fps=30,scale=1920:1080:flags=lanczos,tpad=stop_mode=clone:stop_duration=1,format=yuv420p`, '-t', String(dur),
    '-c:v', 'libx264', '-preset', 'medium', '-crf', '16', '-movflags', '+faststart', mp4]);
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  const report = [];
  for (const n of ONLY) {
    const sc = SCENES[n];
    if (!sc) continue;
    const dir = path.join(OUT, `scene-${n}`);
    fs.rmSync(dir, { recursive: true, force: true }); fs.mkdirSync(dir, { recursive: true });
    const ctx = await browser.newContext({ viewport: VIEW, deviceScaleFactor: DSF, locale: 'ko-KR' });
    const page = await ctx.newPage();
    const errs = [];
    page.on('pageerror', e => errs.push(String(e)));
    page.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
    await page.goto(BASE + sc.url, { waitUntil: 'networkidle' });
    await sleep(600);
    const state = { stop: false, t0: performance.now() };
    const marks = [];
    const now = () => (performance.now() - state.t0) / 1000;
    const mark = what => { marks.push([+now().toFixed(2), what]); console.log(`  [${n}] ${now().toFixed(1)}s ${what}`); };
    const at = async s => { const w = s - now(); if (w > 0) await sleep(w * 1000); };
    console.log(`장면 ${n} ${sc.name} (${sc.dur}초) ${BASE + sc.url}`);
    const cap = capture(page, dir, state);
    try { await sc.run({ page, at, mark }); } catch (e) { mark('⚠ 동작 실패: ' + String(e).slice(0, 160)); }
    await at(sc.dur);
    state.stop = true;
    const frames = (await cap).filter(([, t]) => t < sc.dur);
    const sw = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
    fs.writeFileSync(path.join(dir, 'timeline.json'), JSON.stringify({ scene: n, name: sc.name, url: BASE + sc.url, dur: sc.dur, marks, frames: frames.length, errors: errs }, null, 1));
    await ctx.close();
    const mp4 = path.join(OUT, `scene-${n}.mp4`);
    encode(dir, frames, sc.dur, mp4);
    const fps = (frames.length / sc.dur).toFixed(1);
    if (frames.length / sc.dur < 12) marks.push([sc.dur, `⚠ 프레임 ${fps}/초 — 컴퓨터가 바쁠 때 찍힘(끊겨 보임) · 한가할 때 다시`]);
    report.push(`장면 ${n} ${sc.name}: ${mp4} · 프레임 ${frames.length}장(${fps}/초) · 콘솔 에러 ${errs.length} · 가로 넘침 ${sw > 0 ? sw + 'px' : 0} · ${marks.filter(m => m[1].startsWith('⚠')).map(m => m[1]).join(' ') || '경고 없음'}`);
  }
  await browser.close();
  console.log('\n' + report.join('\n'));
})();
