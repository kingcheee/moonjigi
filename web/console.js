/* 문지기 콘솔 — console.html이 쓴다. moonjigi.js(시연 화면과 같이 쓰는 스크립트) 뒤에 읽힌다. 빌드 도구 없음.

   칸 넷과 데이터가 오는 곳 — 화면의 숫자·판정은 전부 서버 응답이다. 지어낸 행은 없고, 비면 「0건」.
   - 승인 대기 #approvals : GET /worker/runs 의 안 끝난 판 → GET /worker/events 가 live && waiting 인 것 → POST /worker/confirm
                            (Zoro-1 일꾼 판만. 다른 에이전트(MCP) 건은 허락하는 길이 서버에 없다 — 검문 기록에 「보류」로만 보인다)
   - 검문 기록 #log       : GET /log?n=50 — HTTP로 들어온 검문(다른 에이전트의 호출 · try.html의 묻기). 2초마다 읽어 새 줄을 위에 붙인다
   - 규칙 #rules          : GET /health 의 rules. 서버는 「켜 둔 상태」를 저장하지 않는다(요청마다 넘긴다) — 스위치를 그리지 않는다
   - 연결 #connect        : 등록 명령(정적) · GET /health 의 정책 판 · GET /worker/runs 의 MCP 판

   말투: 라벨·값·단추만. 문장을 화면에 내지 않고, 낱말은 명사로 끝낸다(시연 화면과 같은 기준). api()의 오류 글도 내지 않는다.
   녹화용 이름: #approvals #log #rules #connect · [data-log-row][data-decision=PASS|CONFIRM|BLOCK|REASON]
               · [data-approval] 안의 [data-approve] [data-deny] · [data-filter] · [data-nav] · #connect-cmd · [data-conn] */
(() => {
"use strict";

const LOG_N = 50;                                   // 검문 기록을 몇 줄 읽나
const EVERY = {log:2000, runs:4000, health:15000};  // 다시 읽는 간격(ms). /worker/runs는 서버가 판 파일을 100개까지 읽고, /health는 판정 서버까지 다녀오므로 드물게
const THINK_S = 60;                                 // 「더 따져 보는 중」으로 보는 시간. 지나도 최종 판정이 없으면 「미결」
const OPEN_S = 600;                                 // 안 끝난 MCP 판을 「연결 중」으로 보는 시간(마지막 기록부터)
const PAST_RUNS = 24;                               // 처리 기록 · 최근 연결을 찾으려고 여는 끝난 판 수(한 번 읽으면 다시 읽지 않는다)
const SHOW_DONE = 8, SHOW_CONN = 5;
const PANELS = ["approvals", "log", "rules", "connect"];

// 낱말 — 시연 화면(moonjigi.js)과 같은 말을 쓴다
const RULE_NAME = {pii:"계좌번호·주민등록번호"};                                  // 회사 규칙의 짧은 이름. 없으면 규칙 id
const DECISION = {PASS:["통과", "pass"], CONFIRM:["보류", "ask"], BLOCK:["차단", "block"]};   // 검문 기록의 결정 → [낱말, 색]
const MCP_TOOLS = ["list_mail", "read_mail", "search_files", "read_doc", "list_events", "move_file", "create_event", "send_email", "share_link", "delete_file"];   // mcp/README.md
// 걸린 정책 줄 → 짧은 사유. moonjigi.js에 whyParts()가 있으면 그 말을 쓰고, 없으면 같은 표를 여기서 읽는다
const WHY = [
  [/^risky & match<=0\.2$/, "요청 범위 이탈"],
  [/^risky & injected>=0\.8$/, "프롬프트 인젝션"],
  [/^gate unreachable/, "게이트 무응답"],
  [/^gate error/, "검증 서버 연결 실패"],
  [/cut\/timeout/, "추론 타임아웃 / 미완료"],
  [/^still unsure|^risky & unsure/, "신뢰도 낮음"],
  [/^known read-only tool$|^read & injected<0\.5$/, "읽기 전용"],
  [/^match>=0\.8/, "정상 요청 범위"],
];

const C = {
  skew:0,                    // 서버 시계 − 내 시계(ms) — 만료까지 남은 시간에 쓴다
  health:null,
  rows:new Map(),            // 검문 기록: key → {tr, html}
  logFirst:true, filter:"all",
  waiting:new Map(),         // 승인 대기: run|call → {node, it}
  dead:new Set(),            // 파일만 남고 서버에 살아 있지 않은 판
  past:new Map(),            // 끝난 판 run_id → 사람이 답한 호출 목록
  conns:new Map(),           // MCP 판 run_id → 연결 한 줄
  drawn:{},                  // 칸마다 마지막으로 그린 HTML(같으면 다시 그리지 않는다)
};
const el = id => document.getElementById(id);
const now = () => Date.now() + C.skew;
const p2 = n => String(n).padStart(2, "0");
const cut = (s, n) => (s = String(s ?? "")).length > n ? s.slice(0, n - 1) + "…" : s;
const obj = x => (x && typeof x === "object" && !Array.isArray(x)) ? x : {};
function draw(id, html){ if (C.drawn[id] !== html){ el(id).innerHTML = html; C.drawn[id] = html; } }
function text(id, s){ const n = el(id); s = String(s ?? ""); if (n.textContent !== s) n.textContent = s; }
function short(id, s){ s = String(s ?? ""); text(id, s.slice(0, 8)); el(id).title = s; }   // 판 번호는 앞 8자만 보이고 전체는 title에
function hash(s){ let h = 5381; for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0; return (h >>> 0).toString(36); }

// ───────────── 시각 ─────────────
function parseT(t){                                   // "2026-11-19T16:42:53+0900" → ms
  const ms = Date.parse(String(t ?? "").replace(/([+-]\d{2})(\d{2})$/, "$1:$2"));
  return isNaN(ms) ? null : ms;
}
function clock(ms){                                   // 오늘이면 "16:42:53", 다른 날이면 "11-18 16:42"
  if (ms == null) return "";
  const d = new Date(ms), hms = `${p2(d.getHours())}:${p2(d.getMinutes())}:${p2(d.getSeconds())}`;
  return d.toDateString() === new Date(now()).toDateString() ? hms : `${p2(d.getMonth() + 1)}-${p2(d.getDate())} ${hms.slice(0, 5)}`;
}

// ───────────── 낱말 ─────────────
function target(name, args){                          // 대상 — 인자 요약(받는 사람 · 파일 이름 …)
  let s = "";
  try { s = toolOf(name).what(obj(args)); } catch (e) {}
  return s === "{}" ? "" : cut(s, 120);
}
function whyLabel(v){
  const r = String((v && v.rule) || "");
  if (/^company rule/.test(r)){
    const hit = (v.rules || []).find(x => x && x.hit);
    const id = hit ? hit.id : (/^company rule: ([\w-]+)/.exec(r) || [])[1];
    return "사내 정책" + (id ? " · " + (RULE_NAME[id] || id) : "");
  }
  if (r === "no rule fired") return "";
  if (typeof whyParts === "function"){ const w = whyParts(v)[0]; if (w && w !== r) return w; }
  const m = WHY.find(([re]) => re.test(r));
  return m ? m[1] : "";                               // 모르는 줄은 칸을 비우고 원문은 title에만 둔다
}

// ───────────── 서버 ─────────────
async function events(run){
  try { return await api(`/worker/events?run=${encodeURIComponent(run)}&since=0`); } catch (e) { return null; }
}
async function each(list, fn, k = 4){                 // 한꺼번에 k개까지만
  let i = 0;
  await Promise.all(Array.from({length:Math.min(k, list.length)}, async () => {
    while (i < list.length){ const x = list[i++]; try { await fn(x); } catch (e) {} }
  }));
}
function build(evs){ const S = newRun(); for (const ev of evs || []) applyEvent(S, ev); return S; }
const isMcp = r => / · MCP$/.test(String(r.worker_prompt || ""));
const isLiveKind = r => /^\d{6}-/.test(String(r.run_id || ""));      // 서버 안에서 돈 Zoro-1 일꾼 판(이름이 시각으로 시작한다)

// ───────────── 상태 · 규칙 · 연결의 환경변수 (GET /health) ─────────────
async function tickHealth(){
  let r, h;
  try { r = await fetch(BASE + "/health", {cache:"no-store"}); h = await r.json(); }
  catch (e) { C.health = null; renderStatus("down"); throw e; }
  const date = Date.parse(r.headers.get("date") || "");
  if (!isNaN(date)) C.skew = date + 500 - Date.now();               // Date 머리글은 초 단위
  C.health = obj(h);
  renderStatus(C.health.ok ? "ok" : "bad");
  renderRules(); renderEnv();
}
function renderStatus(state){
  const h = C.health || {}, s = el("status");
  s.dataset.state = state;
  s.className = "health " + (state === "ok" ? "ok" : "bad");
  const word = {ok:"연결", bad:"무응답", down:"연결 실패"}[state];           // 시연 화면의 위 띠와 같은 말
  text("status-text", state === "down" ? "서버 연결 실패" : "검증 서버 " + word);
  text("status-policy", h.policy ? "정책 " + h.policy : "");
  text("st-judge", word);
  el("st-judge").className = state === "ok" ? "t-pass" : "t-block";
  text("st-policy", h.policy || "");
  short("st-policy-v", h.policy_version);
  short("st-rules-v", h.rules_version);
}
function renderRules(){
  const rules = Object.entries(obj((C.health || {}).rules)), ver = (C.health || {}).rules_version;
  text("rules-n", rules.length || ""); text("nav-rules-n", rules.length || "");
  el("rules-none").hidden = rules.length > 0;
  draw("rules-list", rules.map(([id, r]) => `<article class="cn-rule" data-rule="${esc(id)}">
    <p class="cn-rule-text">${esc(r.text || id)}</p>
    <dl class="cn-kv">
      <dt>규칙 ID</dt><dd class="mono">${esc(id)}</dd>
      <dt>대상</dt><dd>${esc(KIND_KO[r.effect] || r.effect || "")}</dd>
      <dt>임계값 (Threshold)</dt><dd>${esc(r.threshold ?? "")}</dd>
      <dt>조치</dt><dd>승인 필요</dd>
      <dt>적용 방식</dt><dd>요청별 지정 (Per-request)</dd>
      <dt>MCP</dt><dd class="mono">MOONJIGI_RULES=${esc(id)}</dd>
      <dt>HTTP</dt><dd class="mono">"rules": ["${esc(id)}"]</dd>
      ${ver ? `<dt>버전</dt><dd class="mono">${esc(ver)}</dd>` : ""}
    </dl></article>`).join(""));
}
function renderEnv(){                                 // 값이 없는 줄은 그리지 않는다
  const h = C.health || {};
  const rows = [["게이트웨이 URL", "MOONJIGI_GATE", location.origin], ["규칙", "MOONJIGI_RULES", Object.keys(obj(h.rules)).join(",")], ["정책 버전", "MOONJIGI_POLICY", h.policy || ""]];
  draw("connect-env", rows.filter(r => r[2]).map(([k, name, val]) => `<dt>${esc(k)}</dt><dd class="mono">${esc(name)}=${esc(val)}</dd>`).join(""));
}
function renderTools(){                               // 정적 — MCP 서버가 내놓는 도구 열(mcp/README.md)
  const by = {};
  for (const n of MCP_TOOLS){ const k = toolOf(n).kind || "read"; (by[k] = by[k] || []).push(n); }
  text("tools-n", MCP_TOOLS.length);
  draw("connect-tools", ["read", "modify", "send", "delete"].filter(k => by[k]).map(k =>
    `<dt>${esc(KIND_KO[k])}</dt><dd class="mono">${by[k].map(esc).join(" · ")}</dd>`).join(""));
}

// ───────────── 검문 기록 (GET /log) ─────────────
// 서버는 오래된 것부터 준다. 한 호출이 두 줄로 올 수 있다 — 바로 답한 줄(REASON)과, 같은 reason_id의 최종 판정 줄. 한 행으로 합친다.
function logModel(entries){
  const rows = [], byRid = new Map(), dup = new Map();
  for (const e of Array.isArray(entries) ? entries : []){
    const v = obj(e && e.verdict), tc = obj(e && e.call && e.call.tool_call), rid = v.reason_id || "";
    if (!tc.name && !v.decision) continue;            // 읽을 수 없는 줄
    if (e.kind === "reason" && rid && byRid.has(rid)){ byRid.get(rid).v = v; continue; }
    let key;
    if (rid) key = "r:" + rid;
    else {                                            // 줄 번호가 없어 내용으로 이름을 짓는다(같은 줄이 또 오면 번호를 붙인다)
      const raw = [e.t, e.kind, tc.name, v.decision, v.rule, obj(v.ms).total, JSON.stringify(tc.args ?? null)].join("|");
      const n = (dup.get(raw) || 0) + 1; dup.set(raw, n);
      key = "k:" + hash(raw) + ":" + n;
    }
    const row = {key, t:parseT(e.t), name:String(tc.name || ""), args:tc.args, v};
    if (rid) byRid.set(rid, row);
    rows.push(row);
  }
  return rows;
}
function decisionOf(row){
  const d = row.v.decision;
  if (d === "REASON") return (row.t != null && now() - row.t < THINK_S * 1000)
    ? {code:"REASON", ko:"추론 중", tone:"muted", busy:true} : {code:"REASON", ko:"미완료", tone:"muted"};
  const x = DECISION[d];
  return x ? {code:d, ko:x[0], tone:x[1]} : {code:String(d || ""), ko:String(d || ""), tone:"muted"};
}
function rowHTML(row, d){
  const v = row.v, ms = obj(v.ms).total, tgt = target(row.name, row.args), why = d.code === "REASON" ? "" : whyLabel(v);
  return `<td class="cn-c-time">${esc(clock(row.t))}</td>
<td class="cn-c-tool">${esc(cut(toolOf(row.name).ko, 40))}</td>
<td class="cn-c-target" title="${esc(tgt)}">${esc(tgt)}</td>
<td class="cn-c-dec"><span class="cn-d cn-d-${d.tone}${d.busy ? " cn-d-now" : ""}">${esc(d.ko)}</span></td>
<td class="cn-c-why" title="${esc(v.rule || "")}">${esc(why)}</td>
<td class="cn-c-ms">${typeof ms === "number" ? esc(secs(ms)) : ""}</td>`;
}
function renderLog(entries){
  const rows = logModel(entries), body = el("log-rows"), keep = new Set(rows.map(r => r.key));
  for (const [k, x] of C.rows) if (!keep.has(k)){ x.tr.remove(); C.rows.delete(k); }
  for (const row of rows){                            // 오래된 것부터 돈다 → 새 행은 늘 맨 위에 붙는다
    const d = decisionOf(row), html = rowHTML(row, d);
    let x = C.rows.get(row.key);
    if (!x){
      const tr = document.createElement("tr");
      tr.setAttribute("data-log-row", "");
      if (!C.logFirst) tr.className = "cn-new";       // 처음 읽은 줄들은 새 줄이 아니다
      body.prepend(tr);
      x = {tr, html:""}; C.rows.set(row.key, x);
    }
    if (x.html !== html){ x.tr.innerHTML = html; x.html = html; x.tr.dataset.decision = d.code; }
  }
  C.logFirst = false;
  applyFilter();
}
function applyFilter(){
  let n = 0;
  for (const {tr} of C.rows.values()){
    const show = C.filter === "all" || tr.dataset.decision === C.filter;
    if (tr.hidden === show) tr.hidden = !show;
    if (show) n++;
  }
  el("log-none").hidden = n > 0;
  el("log").dataset.filter = C.filter;
}
function setLive(ok){ el("log-live").dataset.state = ok ? "ok" : "bad"; text("log-live-text", ok ? "자동 갱신" : "갱신 중단"); }
async function tickLog(){
  let d;
  try { d = await api("/log?n=" + LOG_N); } catch (e) { setLive(false); throw e; }
  setLive(true);
  renderLog(d);
}

// ───────────── 승인 대기 · 처리 기록 · 최근 연결 (GET /worker/runs → /worker/events) ─────────────
// 사람이 답한 호출(허락 · 거절 · 만료). 기다림 0초로 남은 것(붙은 사람이 없던 판)과 MCP의 보류는 여기 넣지 않는다.
function answered(run, S, evs){
  const out = [];
  for (const id of S.order){
    const c = S.calls.get(id), cf = c.confirm;
    if (!cf || isHeld(cf)) continue;
    const wait = evs.find(e => e.type === "confirm_wait" && e.call_id === id), res = evs.find(e => e.type === "confirm_result" && e.call_id === id);
    if (!wait || !wait.timeout_s || !res) continue;
    out.push({key:run + "|" + id, t:res.t != null ? res.t * 1000 : null, name:c.name, args:c.args,
      word:cf.approve ? "승인" : (cf.by === "timeout" ? "만료" : "거절"), tone:cf.approve ? "pass" : "muted"});
  }
  return out;
}
function connOf(r, evs){
  const S = build(evs), st = S.start || {}, calls = S.order.map(id => S.calls.get(id));
  const n = key => calls.filter(c => outcome(c, S).key === key).length;
  const last = evs.length ? evs[evs.length - 1].t : null;
  const open = !r.done && last != null && now() / 1000 - last < OPEN_S;
  return {id:r.run_id, t:st.t != null ? st.t * 1000 : null, open, settled:!!r.done || !open,
    who:workerName({worker:st.worker || String(r.worker_prompt || "").replace(/ · MCP$/, "")}),
    calls:calls.length, held:n("held"), blocked:n("block")};
}
async function tickRuns(){
  const runs = await api("/worker/runs");
  if (!Array.isArray(runs)) return;

  // 1) 승인 대기 — 안 끝난 일꾼 판 가운데 서버에 살아 있고(live) 사람을 기다리는(waiting) 것만
  const waiting = new Map(), fresh = [];
  await each(runs.filter(r => !r.done && !isMcp(r) && !C.dead.has(r.run_id)), async r => {
    const d = await events(r.run_id);
    if (!d) return;
    if (!d.live){ C.dead.add(r.run_id); return; }
    const evs = d.events || [], S = build(evs);
    fresh.push(...answered(r.run_id, S, evs));
    const c = !d.done && d.waiting ? S.calls.get(d.waiting) : null;
    if (!c) return;
    const w = evs.filter(e => e.type === "confirm_wait" && e.call_id === c.id).pop() || {};
    waiting.set(r.run_id + "|" + c.id, {run:r.run_id, call:c.id, name:c.name, args:obj(c.args), v:c.v || {}, task:(S.start || {}).task || r.task || "", t0:w.t, limit:w.timeout_s});
  });
  renderApprovals(waiting);

  // 2) 처리 기록 — 끝난 판에서 사람이 답한 기록
  const past = runs.filter(r => r.done && isLiveKind(r) && Array.isArray(r.decisions) && r.decisions.includes("CONFIRM")).slice(0, PAST_RUNS);
  await each(past.filter(r => !C.past.has(r.run_id)), async r => {
    const d = await events(r.run_id);
    if (d) C.past.set(r.run_id, answered(r.run_id, build(d.events), d.events || []));
  });
  const done = new Map();
  for (const x of [...fresh, ...past.flatMap(r => C.past.get(r.run_id) || [])]) done.set(x.key, x);
  renderDone([...done.values()].sort((a, b) => (b.t || 0) - (a.t || 0)).slice(0, SHOW_DONE));

  // 3) 최근 연결 — 다른 에이전트(MCP)의 판. 안 끝난 판은 매번 다시 읽는다
  const mcp = runs.filter(isMcp), open = mcp.filter(r => !r.done), closed = mcp.filter(r => r.done).slice(0, PAST_RUNS);
  await each([...open, ...closed].filter(r => !(C.conns.get(r.run_id) || {}).settled), async r => {
    const d = await events(r.run_id);
    if (d) C.conns.set(r.run_id, connOf(r, d.events || []));
  });
  const list = [...open, ...closed].map(r => C.conns.get(r.run_id)).filter(Boolean).sort((a, b) => (b.t || 0) - (a.t || 0));
  renderConns(list.slice(0, SHOW_CONN), mcp.length);
}

function approvalHTML(it){
  const a = it.args, t = toolOf(it.name), tgt = target(it.name, a), rows = [["사유", whyLabel(it.v)]];
  if (it.task) rows.push(["사용자 요청", cut(it.task, 200)]);
  if (it.name === "send_email"){
    if (a.subject) rows.push(["제목", a.subject]);
    if (Array.isArray(a.attach) && a.attach.length) rows.push(["첨부파일", a.attach.map(baseName).join(", ")]);
    if (a.body) rows.push(["본문", a.body, "cn-pre"]);
  } else {
    const rest = Object.entries(a).map(([k, x]) => `${k}=${typeof x === "string" ? x : JSON.stringify(x)}`).join("  ");
    if (rest) rows.push(["인자", cut(rest, 400), "mono"]);
  }
  return `<div class="cn-ap-head">
    <p class="cn-ap-what"><b>${esc(t.ko)}</b>${tgt ? `<span title="${esc(tgt)}">· ${esc(tgt)}</span>` : ""}</p>
    <span class="cn-ap-left">남은 시간 <span data-left></span></span>
    <span class="cn-ap-act"><button type="button" class="b" data-deny>거절</button><button type="button" class="b main" data-approve>승인</button></span>
  </div>
  <dl class="cn-kv">${rows.filter(r => r[1]).map(([k, x, cls]) => `<dt>${esc(k)}</dt><dd${cls ? ` class="${cls}"` : ""}>${esc(x)}</dd>`).join("")}</dl>`;
}
// 행은 run|call 이름으로 붙들어 둔다 — 다시 읽을 때마다 갈아 끼우면 누르던 단추가 사라진다
function renderApprovals(waiting){
  const box = el("ap-list");
  for (const [k, x] of C.waiting) if (!waiting.has(k)){ x.node.remove(); C.waiting.delete(k); }
  for (const [k, it] of waiting){
    const x = C.waiting.get(k);
    if (x){ x.it = it; continue; }
    const node = document.createElement("article");
    node.className = "cn-ap"; node.setAttribute("data-approval", "");
    node.dataset.run = it.run; node.dataset.call = it.call;
    node.innerHTML = approvalHTML(it);
    box.append(node);
    C.waiting.set(k, {node, it});
  }
  const n = C.waiting.size;
  text("ap-n", n); el("ap-n").dataset.n = n; text("nav-ap-n", n || "");
  el("ap-none").hidden = n > 0;
  el("approvals").dataset.pending = n;                 // 넓은 화면에서는 기다리는 건이 있으면 처리 기록을 접는다(console.css)
  document.title = (n ? `(${n}) ` : "") + "문지기 콘솔";
  tickLeft();
}
function tickLeft(){                                  // 사람 확인이 만료될 때까지 남은 시간
  for (const {node, it} of C.waiting.values()){
    const out = node.querySelector("[data-left]");
    if (!out) continue;
    if (it.t0 == null || !it.limit){ out.textContent = ""; continue; }
    const s = Math.max(0, Math.ceil(it.limit - (now() / 1000 - it.t0)));
    const str = Math.floor(s / 60) + ":" + p2(s % 60);
    if (out.textContent !== str) out.textContent = str;
  }
}
async function answer(node, approve){
  const run = node.dataset.run, call = node.dataset.call;
  node.querySelectorAll("button").forEach(b => { b.disabled = true; });
  node.dataset.sent = approve ? "approve" : "deny";
  try {                                               // 서버의 허락은 「그 판이 지금 기다리는 호출」에 걸린다 — 보내기 직전에 같은 호출인지 다시 본다
    const d = await api(`/worker/events?run=${encodeURIComponent(run)}&since=0`);
    if (d.live && !d.done && d.waiting === call) await api("/worker/confirm", {run, approve});
  } catch (e) {}
  LOOPS.runs();
}
function renderDone(list){
  el("ap-done-box").hidden = !list.length;
  draw("ap-done", list.map(x => { const tgt = target(x.name, x.args); return `<li data-done="${esc(x.key)}">
    <span class="cn-t">${esc(clock(x.t))}</span>
    <span class="cn-w"><b>${esc(toolOf(x.name).ko)}</b>${tgt ? " · " + esc(tgt) : ""}</span>
    <span class="cn-r t-${x.tone}">${esc(x.word)}</span></li>`; }).join(""));
}
function renderConns(list, total){
  text("conn-n", total || "");
  el("conn-none").hidden = list.length > 0;
  draw("conn-list", list.map(x => `<li data-conn="${esc(x.id)}" data-open="${x.open}">
    <span class="cn-who">${esc(x.who)}</span><span class="cn-st">${x.open ? "연결 중" : ""}</span>
    <span class="cn-meta">${esc(clock(x.t))} · 호출 ${x.calls}${x.held ? ` · <b class="t-ask">보류 ${x.held}</b>` : ""}${x.blocked ? ` · <b class="t-block">차단 ${x.blocked}</b>` : ""}</span></li>`).join(""));
}

// ───────────── 메뉴(좁은 화면에서는 탭) · 거르기 · 복사 ─────────────
function setTab(name, move){
  if (!PANELS.includes(name)) name = "log";
  document.body.dataset.tab = name;
  for (const a of document.querySelectorAll("[data-nav]")){
    if (a.dataset.nav === name) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  }
  if (move){ const p = el(name); p.scrollIntoView({block:"nearest"}); p.focus({preventScroll:true}); }
}
async function copy(btn){
  const src = document.querySelector(btn.dataset.copy);
  if (!src) return;
  const str = src.textContent.trim();
  let ok = false;
  try { if (window.isSecureContext && navigator.clipboard){ await navigator.clipboard.writeText(str); ok = true; } } catch (e) {}
  if (!ok){                                           // http로 열면 clipboard가 없다 — 글을 골라 복사하고, 그것도 안 되면 골라 둔 채로 둔다
    const range = document.createRange(), sel = getSelection();
    range.selectNodeContents(src); sel.removeAllRanges(); sel.addRange(range);
    try { ok = document.execCommand("copy"); } catch (e) {}
    if (ok) sel.removeAllRanges();
  }
  if (ok){ btn.textContent = "복사 완료"; setTimeout(() => { btn.textContent = "복사"; }, 1200); }
}
document.addEventListener("click", e => {
  const nav = e.target.closest("[data-nav]");
  if (nav){ e.preventDefault(); setTab(nav.dataset.nav, true); history.replaceState(null, "", "#" + nav.dataset.nav); return; }
  const f = e.target.closest("[data-filter]");
  if (f){
    C.filter = f.dataset.filter;
    for (const b of document.querySelectorAll("[data-filter]")) b.setAttribute("aria-pressed", String(b === f));
    applyFilter(); return;
  }
  const c = e.target.closest("[data-copy]");
  if (c){ copy(c); return; }
  const b = e.target.closest("[data-approve],[data-deny]"), node = b && b.closest("[data-approval]");
  if (node && !b.disabled) answer(node, b.hasAttribute("data-approve"));
});
window.addEventListener("hashchange", () => setTab(location.hash.slice(1), true));

// ───────────── 되풀이 — 앞의 읽기가 끝난 뒤에 다음을 건다. 화면이 안 보이면 쉰다 ─────────────
const LOOPS = {};
function loop(name, fn, ms){
  let timer = 0, busy = false, again = false;
  const run = async () => {
    clearTimeout(timer);
    if (busy){ again = true; return; }
    if (document.hidden) return;                      // 다시 보이면 visibilitychange가 깨운다
    busy = true;
    try { await fn(); } catch (e) {}
    busy = false;
    if (again){ again = false; run(); } else timer = setTimeout(run, ms);
  };
  LOOPS[name] = run;
  run();
}
document.addEventListener("visibilitychange", () => { if (!document.hidden) for (const k in LOOPS) LOOPS[k](); });

setTab(location.hash.slice(1), false);
renderTools(); renderEnv();
loop("health", tickHealth, EVERY.health);
loop("log", tickLog, EVERY.log);
loop("runs", tickRuns, EVERY.runs);
setInterval(tickLeft, 500);
})();
