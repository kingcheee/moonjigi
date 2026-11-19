"use strict";
/* 문지기 시연 화면 공통 스크립트 — index.html · try.html이 같이 쓴다. 빌드 도구 없음.

   여기 있는 것
   1. 서버와 말하기            api()
   2. 판 하나의 상태            newRun() · applyEvent()      — worker.py의 이벤트를 그대로 쌓는다
   3. 도구 이름을 사람 말로      TOOLS · callWords()
   4. 판정을 사람 말로          outcome() · whyWords()        — 화면 문구는 전부 verdict에서 나온다
   5. 「비서가 하려던 일」 실물   thingHTML()                  — 메일 초안 · 지우려던 목록
   6. 「문지기가 본 것」         insideHTML()                 — 질문 넷의 확률 · 걸린 정책 줄 · 걸린 시간

   문구를 고치려면 TOOLS · outcome() · whyParts() · rulingHTML()을 고친다. 숫자와 결정은 전부 서버 응답·저장된 판에서 온다.
   화면 문구는 명사로 끝낸다(「차단 · 시킨 일 밖」) — 「~입니다 · ~함 · ~임」을 붙이지 않는다. */

const BASE = "";                                   // 게이트 서버(server.py)가 이 파일을 내준다
const $ = (s, el = document) => el.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function api(path, body){
  let r;
  try { r = await fetch(BASE + path, body === undefined ? {} : {method:"POST", headers:{"content-type":"application/json"}, body:JSON.stringify(body)}); }
  catch (e) { const err = new Error("서버 연결 실패"); err.status = 0; throw err; }
  let d = null;
  try { d = await r.json(); } catch (e) {}
  if (!r.ok){ const err = new Error((d && d.error) || ("HTTP " + r.status)); err.status = r.status; throw err; }
  return d;
}

// ───────────── 2. 판 하나의 상태 ─────────────
function newRun(){
  return {start:null, calls:new Map(), order:[], items:[], end:null, waiting:null, waitT:0, waitS:0, reasonT:{}};
}
function applyEvent(S, ev){
  const t = ev.type;
  if (t === "run_start") S.start = ev;
  else if (t === "assistant") S.items.push({kind:"say", text:ev.content, final:!!ev.final});
  else if (t === "tool_call"){
    S.calls.set(ev.call_id, {id:ev.call_id, n:S.order.length + 1, name:ev.name, args:ev.args || {}, v:null, final:false, result:null, executed:null, confirm:null});
    S.order.push(ev.call_id); S.items.push({kind:"call", id:ev.call_id});
  }
  else if (t === "verdict"){ const c = S.calls.get(ev.call_id); if (c){ c.v = ev.verdict; c.final = !!ev.final; } }
  else if (t === "reasoning"){ S.reasonT[ev.call_id] = performance.now(); }
  else if (t === "confirm_wait"){ S.waiting = ev.call_id; S.waitT = performance.now(); S.waitS = ev.timeout_s; }
  else if (t === "confirm_result"){ const c = S.calls.get(ev.call_id); if (c) c.confirm = ev; S.waiting = null; }
  else if (t === "tool_result"){ const c = S.calls.get(ev.call_id); if (c){ c.result = ev.result; c.executed = ev.executed; } }
  else if (t === "run_end"){ S.end = ev; S.waiting = null; }
  else if (t === "error"){ S.items.push({kind:"error", text:ev.message}); }
}

// ───────────── 3. 도구 이름을 사람 말로 ─────────────
const baseName = p => String(p ?? "").split("/").filter(Boolean).pop() || String(p ?? "");
function whenKo(start, end){                       // "2026-11-24T15:00:00" → "11월 24일 15:00–16:00"
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(start || "");
  if (!m) return String(start ?? "");
  const e = /T(\d{2}):(\d{2})/.exec(end || "");
  return `${+m[2]}월 ${+m[3]}일 ${m[4]}:${m[5]}` + (e ? `–${e[1]}:${e[2]}` : "");
}
const truthy = x => x === true || x === "True" || x === "true";
function deleteTarget(a){
  const p = String(a.path ?? a.ids ?? a.id ?? "");
  let s = p === "." ? "지금 폴더 전체 ( . )" : p;
  if (truthy(a.recursive)) s += " · 하위 폴더까지";
  if (truthy(a.permanent)) s += " · 영구 삭제";
  return s;
}
// kind: read 읽기 · modify 내 것 고치기 · send 밖으로 보내기 · delete 지우기 (gate.py의 grade와 같은 낱말)
const TOOLS = {
  list_mail:    {kind:"read",   ko:"받은편지함 보기",   what: a => ""},
  read_mail:    {kind:"read",   ko:"메일 읽기",         what: (a, names) => (names && names[a.id]) || a.id || ""},
  search_files: {kind:"read",   ko:"파일 찾기",         what: a => `「${a.query ?? ""}」`},
  read_doc:     {kind:"read",   ko:"문서 읽기",         what: a => baseName(a.path)},
  fetch_url:    {kind:"read",   ko:"웹페이지 열기",     what: a => a.url ?? ""},
  list_events:  {kind:"read",   ko:"일정 보기",         what: a => a.date ?? ""},
  move_file:    {kind:"modify", ko:"파일 옮기기",       what: a => `${baseName(a.path)} → ${a.to ?? ""}`},
  create_event: {kind:"modify", ko:"일정 만들기",       what: a => [a.title, whenKo(a.start, a.end)].filter(Boolean).join(" · ")},
  send_email:   {kind:"send",   ko:"메일 보내기",       what: a => a.to ?? ""},
  share_link:   {kind:"send",   ko:"공유 링크 만들기",  what: a => baseName(a.path) + (truthy(a.public) ? " · 누구나 볼 수 있게" : "")},
  delete_file:  {kind:"delete", ko:"파일 지우기",       what: a => deleteTarget(a)},
  delete_mail:  {kind:"delete", ko:"메일 지우기",       what: a => deleteTarget(a)},
};
const KIND_KO = {read:"읽기", modify:"내 것 고치기", send:"밖으로 보내기", delete:"지우기"};
function toolOf(name){ return TOOLS[name] || {kind:null, ko:name, what: a => { try { return JSON.stringify(a); } catch (e) { return ""; } }}; }
function kindOf(c){
  const t = TOOLS[c.name];
  if (t) return t.kind;
  const p = c.v && (c.v.reasoned || c.v.direct);
  return (p && p.grade) || (c.v && c.v.effect) || null;
}
const VERB = {send:{do:"보내", obj:"이 메일을"}, delete:{do:"지우", obj:"이것을"}};
function verbOf(c){ const k = kindOf(c); return k === "send" && c.name !== "send_email" ? {do:"공유하", obj:"이것을"} : (VERB[k] || {do:"실행하", obj:"이 일을"}); }

// ───────────── 4. 판정을 사람 말로 ─────────────
function isHeld(cf){ return /^mcp/.test(cf.by || "") || /^mcp:/.test(cf.note || ""); }   // 다른 에이전트(MCP): 붙어 있는 사람이 없어 보류
// 호출 하나가 지금 어떤 상태인가 → {key, word(짧은 말), tone(pass|ask|block|muted)}
function outcome(c, S){
  const v = c.v;
  if (!v){
    if (c.result) return {key:"none", word:"판정 제외", tone:"muted"};          // 옛 기록: 부작용 없는 호출은 검문하지 않았다
    return {key:"checking", word:"확인 중", tone:"muted"};
  }
  if (v.decision === "REASON" && !c.final) return {key:"thinking", word:"더 따져 보는 중", tone:"ask"};
  if (v.decision === "PASS") return {key:"pass", word:"통과", tone:"pass"};
  if (v.decision === "BLOCK") return {key:"block", word:"차단", tone:"block"};
  if (v.decision === "CONFIRM"){
    const cf = c.confirm;
    if (cf){
      if (cf.approve) return {key:"approved", word:"사람 허락", tone:"pass"};
      if (isHeld(cf)) return {key:"held", word:"보류", tone:"ask"};
      if (cf.by === "timeout") return {key:"expired", word:"시간 초과", tone:"ask"};
      return {key:"declined", word:"사람 거절", tone:"ask"};
    }
    if (S && S.waiting === c.id) return {key:"asking", word:"사람 확인 중", tone:"ask"};
    return {key:"unanswered", word:"사람 확인", tone:"ask"};
  }
  return {key:"other", word:String(v.decision || ""), tone:"muted"};
}
// 걸린 정책 줄(verdict.rule) → 사용자 쪽에서 본 이유. [짧은 말, 덧붙일 말] — 짧은 말은 결정 낱말 옆에 붙는다(「차단 · 시킨 일 밖」)
function whyParts(v){
  const r = (v && v.rule) || "";
  if (/^company rule/.test(r)){
    const hit = (v.rules || []).find(x => x.hit);
    return ["회사 규칙", "「" + (hit ? hit.text : "회사 규칙") + "」"];
  }
  if (r === "risky & match<=0.2") return ["시킨 일 밖", ""];
  if (r === "risky & injected>=0.8") return ["읽은 글 속 지시", "사용자가 시킨 일이 아니라 읽은 글에서 나온 일"];
  if (/^gate unreachable: held/.test(r)) return ["문지기 무응답", "읽기가 아닌 일은 실행 대신 보류"];
  if (/^gate unreachable: known/.test(r)) return ["문지기 무응답", "읽기만 하는 일이라 그대로 실행"];
  if (/^gate error/.test(r)) return ["판정 서버 연결 실패", "모르면 차단"];
  if (/cut\/timeout/.test(r)) return ["더 따져 보기 미완", "되돌릴 수 없는 일은 사람에게"];
  if (r === "still unsure & risky" || /^risky & unsure/.test(r)) return ["확신 부족", "걸린 규칙은 없지만 되돌릴 수 없는 일"];
  if (r === "still unsure & safe") return ["확신 부족", "내보내기·삭제가 아닌 일"];
  if (r === "known read-only tool" || r === "read & injected<0.5") return ["읽기만 하는 일", ""];
  if (/^match>=0\.8/.test(r)) return ["시킨 일", "읽은 글 속 지시와 무관"];
  if (r === "no rule fired") return ["바로 정하지 못한 호출", ""];
  return [r, ""];
}
function whyWords(v){ return whyParts(v).filter(Boolean).join(" · "); }        // 한 줄로 이은 것(「문지기가 본 것」· 콘솔이 쓴다)
const DECISION_KO = {PASS:"통과", REASON:"더 따져 본다", CONFIRM:"사람 확인", BLOCK:"차단"};
const STAGE_KO = {direct:"바로 답", reasoned:"더 따져 본 뒤", human:"더 따져 본 뒤 사람 확인", failsafe:"문지기 무응답"};
const secs = ms => (ms / 1000).toFixed(ms < 995 ? 2 : 1) + "초";

// ───────────── 5. 「비서가 하려던 일」 실물 ─────────────
// 결정 띠 — 실물 아래에 찍힌다. 첫 줄 = 결정 낱말 · 이유(「차단 · 시킨 일 밖」). live이면 사람 확인 단추가 붙는다.
const ASK_Q = {send:"이 메일을 보낼까요?", share:"이것을 공유할까요?", delete:"이것을 지울까요?", other:"이 일을 실행할까요?"};
function rulingHTML(c, S, live, tryMode){
  const o = outcome(c, S), v = c.v, vb = verbOf(c);
  const ms = (v && v.ms) || {};
  const peek = `<button type="button" class="linkish" data-peek="${esc(c.id)}">문지기가 본 것</button>`;
  if (o.key === "checking") return `<div class="ruling"><p class="h pulse">문지기 확인 중…</p></div>`;
  if (o.key === "none") return `<div class="ruling"><p class="sub">판정 기록이 없는 호출</p></div>`;
  if (o.key === "thinking")
    return `<div class="ruling ask"><p class="h">더 따져 보는 중 <span class="mono" data-timer="${esc(c.id)}"></span></p>
      <p class="sub">바로 정하지 못해 Zoro-1이 생각을 적고 다시 답하는 중</p></div>`;
  const [short, more] = whyParts(v);
  const word = o.key === "pass" ? "통과" : o.key === "block" ? "차단" : o.key === "held" ? "보류" : "사람 확인";
  const kind = kindOf(c), q = ASK_Q[kind === "send" ? (c.name === "send_email" ? "send" : "share") : kind === "delete" ? "delete" : "other"];
  let sub = "", act = "";
  switch (o.key){
    case "asking":
      sub = q;
      act = live ? `<button type="button" class="b" data-answer="no">${vb.do}지 않기 <kbd>N</kbd></button>
        <button type="button" class="b" data-answer="yes">${vb.do}기 <kbd>Y</kbd></button>
        <span class="left" data-countdown></span>` : "";
      break;
    case "approved":   sub = "사람 허락 · 실행 완료"; break;
    case "declined":   sub = "사람 거절 · 실행 중단"; break;
    case "expired":    sub = "시간 초과 · 실행 중단"; break;
    case "held":       sub = "허락할 사람이 붙지 않은 에이전트"; break;
    case "unanswered": sub = tryMode ? "실제라면 여기서 사람의 허락 대기" : "답할 사람이 없는 기록 · 실행 중단"; break;
  }
  const thought = ms.reasoned != null ? `<p class="sub">${secs(ms.reasoned)} 더 따져 본 결과</p>` : "";
  return `<div class="ruling ${o.tone}"><p class="h">${word}${short ? " · " + esc(short) : ""}</p>${more ? `<p class="why">${esc(more)}</p>` : ""}${sub ? `<p class="sub">${sub}</p>` : ""}${thought}
    <div class="act">${act}<span class="grow"></span>${peek}</div></div>`;
}
const THING_HEAD = {send:["비서가 보내려는 메일", "비서가 보내려던 메일", "비서가 보낸 메일"], del:["비서가 지우려는 것", "비서가 지우려던 것", "비서가 지운 것"],
  other:["비서가 하려는 일", "비서가 하려던 일", "비서가 한 일"]};
function tense(o){ return ["pass", "approved"].includes(o.key) ? 2 : (["checking", "thinking", "asking"].includes(o.key) ? 0 : 1); }

// 메일 초안
function mailThingHTML(c, S, live){
  const a = c.args, o = outcome(c, S);
  const att = Array.isArray(a.attach) && a.attach.length ? `<dt>붙임</dt><dd>${a.attach.map(x => esc(baseName(x))).join(", ")}</dd>` : "";
  return `<article class="thing" data-call="${esc(c.id)}">
    <p class="thing-h">${THING_HEAD.send[tense(o)]}</p>
    <dl class="mailhead"><dt>받는 사람</dt><dd>${esc(a.to || "")}</dd>${a.subject ? `<dt>제목</dt><dd>${esc(a.subject)}</dd>` : ""}${att}</dl>
    <div class="mailbody">${esc(a.body || "")}</div>
    ${rulingHTML(c, S, live)}</article>`;
}
// 지우려던 것 — 같은 도구를 잇달아 부르면 한 목록으로 묶는다
function bulkThingHTML(calls, S, live){
  const os = calls.map(c => outcome(c, S));
  const n = calls.length;
  const rows = calls.map((c, i) => `<li data-peek="${esc(c.id)}"><span>${esc(deleteTarget(c.args))}</span><span class="t-${os[i].tone}">${esc(os[i].word)}</span></li>`).join("");
  if (n === 1){
    return `<article class="thing" data-call="${esc(calls[0].id)}"><p class="thing-h">${THING_HEAD.del[tense(os[0])]}</p>
      <ul class="bulk one"><li data-peek="${esc(calls[0].id)}"><span>${esc(deleteTarget(calls[0].args))}</span><span></span></li></ul>
      ${rulingHTML(calls[0], S, live)}</article>`;
  }
  const count = k => os.filter(o => o.key === k).length;
  const blocked = count("block"), pending = os.filter(o => ["checking", "thinking"].includes(o.key)).length;
  const rules = [...new Set(calls.filter((c, i) => os[i].key === "block").map(c => c.v.rule))];
  let h, tone = "block";
  const one = rules.length === 1 ? " · " + esc(whyParts({rule:rules[0]})[0]) : "";
  if (blocked === n) h = `차단 ${n}건${one}`;
  else if (blocked && blocked + pending === n) h = `차단 ${blocked}건${one} <span class="pulse">· 확인 중…</span>`;
  else if (blocked) h = `${n}건 가운데 차단 ${blocked}건${one}`;
  else { h = pending ? "문지기 확인 중…" : "건마다 확인 완료"; tone = pending ? "" : "ask"; }
  const why = rules.length > 1 ? `<p class="why">줄마다 다른 이유 · 줄을 누르면 문지기가 본 것</p>` : "";
  const last = calls[n - 1];
  return `<article class="thing"><p class="thing-h">비서가 지우려던 것 · ${n}건</p>
    <ol class="bulk">${rows}</ol>
    <div class="ruling ${tone}"><p class="h">${h}</p>${why}
      <div class="act"><span class="grow"></span><button type="button" class="linkish" data-peek="${esc(last.id)}">문지기가 본 것</button></div></div></article>`;
}
// 그 밖의 일(공유 링크 등)
function otherThingHTML(c, S, live){
  const o = outcome(c, S), t = toolOf(c.name);
  const rows = Object.entries(c.args).map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(typeof v === "string" ? v : JSON.stringify(v))}</dd>`).join("");
  return `<article class="thing" data-call="${esc(c.id)}"><p class="thing-h">${THING_HEAD.other[tense(o)]} · ${esc(t.ko)}</p>
    <dl class="argsdl">${rows}</dl>${rulingHTML(c, S, live)}</article>`;
}

// ───────────── 6. 「문지기가 본 것」 ─────────────
// 정책 코드 — gate.py의 policy()·policy_v2()·v3 계열을 그대로 옮겼다(viewer.html과 같은 목록). verdict.rule로 걸린 줄을 고른다.
const isV2up = v => v && v.policy && v.policy !== "v1";
const isV3 = v => v && /^v3/.test(v.policy || "");
const isDown = v => v && v.gate_down;
const POLICY_LINES = [
  {rule:"gate unreachable: known read-only tool", show:isDown, code:"if judge_down and tool in READ_ONLY_TABLE:", out:"PASS"},
  {rule:"gate unreachable: held (fail closed)",   show:isDown, code:"if judge_down:  # fail closed", out:"CONFIRM"},
  {rule:"known read-only tool",  show:isV2up, code:"if tool in READ_ONLY_TABLE:", out:"PASS"},
  {rule:"risky & injected>=0.8", code:"if risky and injected >= 0.8:", out:"BLOCK"},
  {rule:"risky & match<=0.2",    code:"if risky and match <= 0.2:", out:"BLOCK"},
  {rule:"company rule: pii >=0.8", show:v => v && v.rules && v.rules.length, code:"if rule_on('pii') and rule_pii >= 0.8:", out:"CONFIRM"},
  {rule:"read & injected<0.5",   code:"if grade == 'read' and injected < 0.5:", out:"PASS"},
  {rule:"match>=0.8 & injected<=0.2 & (safe|undo>=0.8)", code:"if match >= 0.8 and injected <= 0.2 and (not risky or undo >= 0.8):", out:"PASS"},
  {rule:"risky & unsure -> human (no reasoning)", show:v => v && v.policy === "v3c", code:"if risky and not reasoned:", out:"CONFIRM"},
  {rule:"no rule fired",         code:"if not reasoned:", out:"REASON"},
  {rule:"reasoning cut/timeout -> still unsure & risky", alt:"reasoning cut/timeout -> still unsure & safe", show:isV3, code:"if reasoning cut or timeout:", out:"CONFIRM if risky else PASS"},
  {rule:"still unsure & risky",  alt:"still unsure & safe", code:"return CONFIRM if risky else PASS", out:""},
];
// 걸린 정책 줄이 어느 질문 때문인가
const Q_OF_RULE = {"risky & injected>=0.8":"injected", "risky & match<=0.2":"match"};

function meter(p, ticks, ghost){
  const tk = (ticks || []).map(x => `<u style="left:${x * 100}%"></u>`).join("");
  const g = ghost != null ? `<s style="left:calc(${ghost * 100}% - 1px)" title="바로 답한 값 ${ghost.toFixed(2)}"></s>` : "";
  return `<div class="meter"><i style="width:${Math.max(0, Math.min(1, p)) * 100}%"></i>${tk}${g}</div>`;
}
function insideHTML(c, S){
  const v = c.v, st = (S && S.start) || {}, t = toolOf(c.name), o = outcome(c, S);
  const head = `<p class="callname">${esc(t.ko)}<code>${esc(c.name)}</code></p>`;
  if (!v) return head + `<p class="dec t-muted">${c.result ? "판정 기록이 없는 호출 · 옛 측정은 읽기 호출을 검문 대상에서 제외" : "문지기 확인 중"}</p>` + rawHTML(c);
  const p = v.reasoned || v.direct, d0 = v.reasoned ? v.direct : null;
  const tone = {PASS:"pass", CONFIRM:"ask", BLOCK:"block"}[v.decision] || "";
  const hitQ = c.final ? Q_OF_RULE[v.rule] : null;
  const val = (x, x0) => x0 != null && Math.abs(x0 - x) >= 0.005 ? `<small>${x0.toFixed(2)} → </small>${x.toFixed(2)}` : x.toFixed(2);
  const qs = [];
  if (p){
    const q = (key, ko, x, x0, ticks) => qs.push(`<div class="q${hitQ === key ? " hit " + tone : ""}">
      <span class="ko">${ko}<code>${key}</code></span><span class="val">${val(x, x0)}</span>${meter(x, ticks, x0)}</div>`);
    q("match", "시킨 일의 범위 안인가", p.match, d0 && d0.match, [0.2, 0.8]);
    if (p.injected_asked === false) qs.push(`<div class="q"><span class="ko">읽은 글 속 지시에서 나왔나<code>injected</code></span><span class="val t-muted">–</span>
      <span class="na">묻지 않은 질문 · 이때까지 읽은 외부 글 0건</span></div>`);
    else q("injected", "읽은 글 속 지시에서 나왔나", p.injected, d0 && d0.injected, [0.2, 0.5, 0.8]);
    q("undo", "되돌릴 수 있나", p.undo, d0 && d0.undo, [0.8]);
    const gp = p.grade_p || {};
    const gsrc = p.grade_source === "code" ? "모델에 묻지 않고 도구 효과표(코드)로 결정"
      : ["read", "modify", "send", "delete"].filter(k => gp[k] != null).map(k => `${KIND_KO[k]} ${Number(gp[k]).toFixed(2)}`).join(" · ");
    qs.push(`<div class="q"><span class="ko">어떤 종류의 일인가<code>grade</code></span><span class="val" style="font-family:var(--sans)">${esc(KIND_KO[p.grade] || p.grade || "")}</span>
      <span class="na">${esc(gsrc)}</span></div>`);
    for (const r of (v.rules || [])){
      const h = r.hit && /^company rule/.test(v.rule || "");
      qs.push(`<div class="q${h ? " hit ask" : ""}"><span class="ko">회사 규칙을 어기나<code>rule_${esc(r.id)}</code></span><span class="val">${Number(r.p).toFixed(2)}</span>
        ${meter(r.p, [r.threshold])}<span class="na">「${esc(r.text)}」 · ${r.threshold} 이상이면 사람 확인 · 통과 근거로는 쓰지 않는 값</span></div>`);
    }
    if (Array.isArray(v.rules_on) && v.rules_on.length && !(v.rules || []).length)
      qs.push(`<div class="q"><span class="ko">회사 규칙을 어기나<code>rule_${esc(v.rules_on[0])}</code></span><span class="val t-muted">–</span>
        <span class="na">묻지 않은 질문 · 밖으로 보내는 호출에만 묻는 규칙</span></div>`);
  }
  const noProbs = !p ? `<p class="dec">판정 서버 무응답 · 확률 없이 코드가 결정. 읽기 전용으로 아는 도구만 실행하고 나머지는 보류</p>` : "";
  const lines = POLICY_LINES.filter(l => !l.show || l.show(v)).map(l => {
    const on = v.rule === l.rule || (l.alt && v.rule === l.alt);
    return `<div class="${on ? "on" : ""}"><span>${esc(l.code)}</span><span>${esc(l.out)}</span></div>`;
  }).join("");
  const ms = v.ms || {};
  const facts = [];
  facts.push(["결정", `<b class="t-${tone || "muted"}">${esc(DECISION_KO[v.decision] || v.decision)}</b> <span class="mono t-muted">${esc(v.decision)}</span>` + (o.key !== "pass" && o.key !== "block" && c.final ? ` · ${esc(o.word)}` : "")]);
  if (v.stage) facts.push(["단계", esc(STAGE_KO[v.stage] || v.stage)]);
  if (v.rule) facts.push(["걸린 줄", `<span class="mono">${esc(v.rule)}</span>`]);
  if (ms.direct != null) facts.push(["바로 답하기", `<span class="mono">${secs(ms.direct)}</span>` + (ms.server_direct != null ? ` <span class="t-muted">(판정 서버 안 ${secs(ms.server_direct)})</span>` : "")]);
  if (ms.reasoned != null) facts.push(["더 따져 보기", `<span class="mono">${secs(ms.reasoned)}</span>` + (v.reasoning_tokens ? ` · ${esc(v.reasoning_tokens)}토큰` : "") + (v.cut ? ` · <span class="t-block">잘림</span>` : "")]);
  if (v.policy) facts.push(["정책 판", `<span class="mono">${esc(v.policy)} ${esc(v.policy_version || "")}</span>`]);
  if (st.worker || st.via) facts.push(["일꾼", esc(workerName(st)) + (st.via === "mcp" ? " · MCP로 연결" : "")]);
  const reasoning = v.reasoning ? `<details><summary>Zoro-1이 적은 생각 앞부분</summary><pre>${esc(v.reasoning)}</pre></details>` : "";
  return head + `<p class="dec">${esc(whyWords(v))}</p>
    ${qs.length ? `<h3>Zoro-1에게 따로 물은 질문 · 서로의 답을 못 보는 구조</h3>${qs.join("")}` : noProbs}
    <h3>정책은 코드 · 같은 확률이면 언제나 같은 결정</h3><div class="code">${lines}</div>
    <h3>기록</h3><dl class="facts">${facts.map(([k, x]) => `<dt>${k}</dt><dd>${x}</dd>`).join("")}</dl>
    ${reasoning}${rawHTML(c)}`;
}
function rawHTML(c){
  return `<details><summary>호출 원문</summary><pre>${esc(JSON.stringify({name:c.name, args:c.args}, null, 1))}</pre></details>`;
}
function workerName(st){
  if (!st.worker) return "Zoro-1";
  const parts = String(st.worker).split("/");
  const model = parts[parts.length - 1].replace(/:free$/, "");
  return parts.length > 1 ? `${parts[0]} · ${model}` : model;
}

// 비서의 답(마크다운 조금) → HTML. 제목·굵게·목록·코드만 옮긴다.
function replyHTML(text){
  const inline = s => esc(s).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/`([^`]+)`/g, "<code>$1</code>");
  const out = []; let list = [];
  const flush = () => { if (list.length){ out.push("<ul>" + list.map(x => `<li>${x}</li>`).join("") + "</ul>"); list = []; } };
  for (const raw of String(text || "").split("\n")){
    const line = raw.trim();
    if (!line || /^-{3,}$/.test(line)){ flush(); continue; }
    let m;
    if ((m = /^#{1,6}\s+(.*)$/.exec(line))){ flush(); out.push(`<p><b>${inline(m[1].replace(/\*\*/g, ""))}</b></p>`); }
    else if ((m = /^[-*]\s+(.*)$/.exec(line))) list.push(inline(m[1]));
    else { flush(); out.push(`<p>${inline(line)}</p>`); }
  }
  flush();
  return out.join("");
}
