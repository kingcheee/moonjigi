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
  let s = p === "." ? "현재 디렉토리 전체 (.)" : p;
  if (truthy(a.recursive)) s += " · 하위 폴더까지";
  if (truthy(a.permanent)) s += " · 영구 삭제";
  return s;
}
// kind: read 읽기 · modify 내 것 고치기 · send 밖으로 보내기 · delete 지우기 (gate.py의 grade와 같은 낱말)
const TOOLS = {
  list_mail:    {kind:"read",   ko:"메일 목록 조회",    what: a => ""},
  read_mail:    {kind:"read",   ko:"메일 읽기",         what: (a, names) => (names && names[a.id]) || a.id || ""},
  search_files: {kind:"read",   ko:"파일 검색",         what: a => `「${a.query ?? ""}」`},
  read_doc:     {kind:"read",   ko:"문서 읽기",         what: a => baseName(a.path)},
  fetch_url:    {kind:"read",   ko:"웹페이지 조회",     what: a => a.url ?? ""},
  list_events:  {kind:"read",   ko:"일정 보기",         what: a => a.date ?? ""},
  move_file:    {kind:"modify", ko:"파일 이동",         what: a => `${baseName(a.path)} → ${a.to ?? ""}`},
  create_event: {kind:"modify", ko:"일정 생성",         what: a => [a.title, whenKo(a.start, a.end)].filter(Boolean).join(" · ")},
  send_email:   {kind:"send",   ko:"메일 보내기",       what: a => a.to ?? ""},
  share_link:   {kind:"send",   ko:"공유 링크 생성",    what: a => baseName(a.path) + (truthy(a.public) ? " · 전체 공개" : "")},
  delete_file:  {kind:"delete", ko:"파일 삭제",         what: a => deleteTarget(a)},
  delete_mail:  {kind:"delete", ko:"메일 삭제",         what: a => deleteTarget(a)},
};
const KIND_KO = {read:"읽기 (Read)", modify:"수정 (Modify)", send:"외부 전송 (Send)", delete:"삭제 (Delete)"};
function toolOf(name){ return TOOLS[name] || {kind:null, ko:name, what: a => { try { return JSON.stringify(a); } catch (e) { return ""; } }}; }
function kindOf(c){
  const t = TOOLS[c.name];
  if (t) return t.kind;
  const p = c.v && (c.v.reasoned || c.v.direct);
  return (p && p.grade) || (c.v && c.v.effect) || null;
}

// ───────────── 4. 판정을 사람 말로 ─────────────
function isHeld(cf){ return /^mcp/.test(cf.by || "") || /^mcp:/.test(cf.note || ""); }   // 다른 에이전트(MCP): 붙어 있는 사람이 없어 보류
// 호출 하나가 지금 어떤 상태인가 → {key, word(짧은 말), tone(pass|ask|block|muted)}
function outcome(c, S){
  const v = c.v;
  if (!v){
    if (c.result) return {key:"none", word:"검증 생략", tone:"muted"};          // 옛 기록: 부작용 없는 호출은 검문하지 않았다
    return {key:"checking", word:"검증 중", tone:"muted"};
  }
  if (v.decision === "REASON" && !c.final) return {key:"thinking", word:"추론 중", tone:"ask"};
  if (v.decision === "PASS") return {key:"pass", word:"통과", tone:"pass"};
  if (v.decision === "BLOCK") return {key:"block", word:"차단", tone:"block"};
  if (v.decision === "CONFIRM"){
    const cf = c.confirm;
    if (cf){
      if (cf.approve) return {key:"approved", word:"승인됨", tone:"pass"};
      if (isHeld(cf)) return {key:"held", word:"보류", tone:"ask"};
      if (cf.by === "timeout") return {key:"expired", word:"시간 초과", tone:"ask"};
      return {key:"declined", word:"거절됨", tone:"ask"};
    }
    if (S && S.waiting === c.id) return {key:"asking", word:"승인 대기 중", tone:"ask"};
    return {key:"unanswered", word:"승인 필요", tone:"ask"};
  }
  return {key:"other", word:String(v.decision || ""), tone:"muted"};
}
// 걸린 정책 줄(verdict.rule) → 사용자 쪽에서 본 이유. [짧은 말, 덧붙일 말] — 짧은 말은 결정 낱말 옆에 붙는다(「차단 · 시킨 일 밖」)
function whyParts(v){
  const r = (v && v.rule) || "";
  if (/^company rule/.test(r)){
    const hit = (v.rules || []).find(x => x.hit);
    return ["사내 정책", "「" + (hit ? hit.text : "사내 정책") + "」"];
  }
  if (r === "risky & match<=0.2") return ["요청 범위 이탈", ""];
  if (r === "risky & injected>=0.8") return ["프롬프트 인젝션", "사용자 요청이 아니라 외부 컨텍스트에서 나온 일"];
  if (/^gate unreachable: held/.test(r)) return ["게이트 무응답", "읽기가 아닌 일은 실행 대신 보류"];
  if (/^gate unreachable: known/.test(r)) return ["게이트 무응답", "읽기 전용 툴이라 그대로 실행"];
  if (/^gate error/.test(r)) return ["검증 서버 연결 실패", "오류 시 차단 (Fail-Closed)"];
  if (/cut\/timeout/.test(r)) return ["추론 타임아웃 / 미완료", "되돌릴 수 없는 일은 사람에게"];
  if (r === "still unsure & risky" || /^risky & unsure/.test(r)) return ["신뢰도 낮음", "매칭된 규칙은 없지만 되돌릴 수 없는 일"];
  if (r === "still unsure & safe") return ["신뢰도 낮음", "외부 전송·삭제가 아닌 일"];
  if (r === "known read-only tool" || r === "read & injected<0.5") return ["읽기 전용", ""];
  if (/^match>=0\.8/.test(r)) return ["정상 요청 범위", "프롬프트 인젝션과 무관"];
  if (r === "no rule fired") return ["경계 구간 (추론 전환)", ""];
  return [r, ""];
}
function whyWords(v){ return whyParts(v).filter(Boolean).join(" · "); }        // 한 줄로 이은 것(「문지기가 본 것」· 콘솔이 쓴다)
const DECISION_KO = {PASS:"통과", REASON:"심층 추론", CONFIRM:"승인 필요", BLOCK:"차단"};
const STAGE_KO = {direct:"1차 판별 (Direct)", reasoned:"추론 후 판정", human:"추론 후 승인 요청", failsafe:"게이트 무응답 (Fail-Closed)"};
const secs = ms => (ms / 1000).toFixed(ms < 995 ? 2 : 1) + "초";

// ───────────── 5. 「비서가 하려던 일」 실물 ─────────────
// 결정 띠 — 실물 아래에 찍힌다. 첫 줄 = 결정 낱말 · 이유(「차단 · 시킨 일 밖」). live이면 사람 확인 단추가 붙는다.
const ASK_Q = {send:"이 메일을 보낼까요?", share:"이것을 공유할까요?", delete:"이것을 삭제할까요?", other:"이 일을 실행할까요?"};
function rulingHTML(c, S, live, tryMode){
  const o = outcome(c, S), v = c.v;
  const ms = (v && v.ms) || {};
  const peek = `<button type="button" class="linkish" data-peek="${esc(c.id)}">판별 상세</button>`;
  if (o.key === "checking") return `<div class="ruling"><p class="h pulse">검증 중…</p></div>`;
  if (o.key === "none") return `<div class="ruling"><p class="sub">판정 기록이 없는 호출</p></div>`;
  if (o.key === "thinking")
    return `<div class="ruling ask"><p class="h">추론 중 <span class="mono" data-timer="${esc(c.id)}"></span></p>
      <p class="sub">경계 구간이라 Zoro-1이 CoT(추론 과정) 생성 후 재판별 중</p></div>`;
  const [short, more] = whyParts(v);
  const word = o.key === "pass" ? "통과" : o.key === "block" ? "차단" : o.key === "held" ? "보류" : "승인 필요";
  const kind = kindOf(c), q = ASK_Q[kind === "send" ? (c.name === "send_email" ? "send" : "share") : kind === "delete" ? "delete" : "other"];
  let sub = "", act = "";
  switch (o.key){
    case "asking":
      sub = q;
      act = live ? `<button type="button" class="b" data-answer="no">거절 <kbd>N</kbd></button>
        <button type="button" class="b" data-answer="yes">승인 <kbd>Y</kbd></button>
        <span class="left" data-countdown></span>` : "";
      break;
    case "approved":   sub = "승인됨 · 실행 완료"; break;
    case "declined":   sub = "거절됨 · 실행 중단"; break;
    case "expired":    sub = "시간 초과 · 실행 중단"; break;
    case "held":       sub = "승인 채널 없음 (자동 보류)"; break;
    case "unanswered": sub = tryMode ? "실제라면 여기서 승인 대기" : "미응답 리플레이 기록 · 실행 중단"; break;
  }
  const thought = ms.reasoned != null ? `<p class="sub">${secs(ms.reasoned)} 심층 추론 결과</p>` : "";
  return `<div class="ruling ${o.tone}"><p class="h">${word}${short ? " · " + esc(short) : ""}</p>${more ? `<p class="why">${esc(more)}</p>` : ""}${sub ? `<p class="sub">${sub}</p>` : ""}${thought}
    <div class="act">${act}<span class="grow"></span>${peek}</div></div>`;
}
const THING_HEAD = {send:["에이전트가 보내려는 메일", "에이전트가 보내려던 메일", "에이전트가 보낸 메일"], del:["에이전트가 삭제하려는 항목", "에이전트가 삭제하려던 항목", "에이전트가 삭제한 항목"],
  other:["호출 예정 툴", "시도한 툴 호출", "툴 호출 내역"]};
function tense(o){ return ["pass", "approved"].includes(o.key) ? 2 : (["checking", "thinking", "asking"].includes(o.key) ? 0 : 1); }

// 메일 초안
function mailThingHTML(c, S, live){
  const a = c.args, o = outcome(c, S);
  const att = Array.isArray(a.attach) && a.attach.length ? `<dt>첨부파일</dt><dd>${a.attach.map(x => esc(baseName(x))).join(", ")}</dd>` : "";
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
  else if (blocked && blocked + pending === n) h = `차단 ${blocked}건${one} <span class="pulse">· 검증 중…</span>`;
  else if (blocked) h = `${n}건 가운데 차단 ${blocked}건${one}`;
  else { h = pending ? "검증 중…" : "건별 검증 완료"; tone = pending ? "" : "ask"; }
  const why = rules.length > 1 ? `<p class="why">항목마다 다른 이유 · 항목을 누르면 판별 상세</p>` : "";
  const last = calls[n - 1];
  return `<article class="thing"><p class="thing-h">에이전트가 삭제하려던 항목 · ${n}건</p>
    <ol class="bulk">${rows}</ol>
    <div class="ruling ${tone}"><p class="h">${h}</p>${why}
      <div class="act"><span class="grow"></span><button type="button" class="linkish" data-peek="${esc(last.id)}">판별 상세</button></div></div></article>`;
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
  const g = ghost != null ? `<s style="left:calc(${ghost * 100}% - 1px)" title="1차 판별값 ${ghost.toFixed(2)}"></s>` : "";
  return `<div class="meter"><i style="width:${Math.max(0, Math.min(1, p)) * 100}%"></i>${tk}${g}</div>`;
}
function insideHTML(c, S){
  const v = c.v, st = (S && S.start) || {}, t = toolOf(c.name), o = outcome(c, S);
  const head = `<p class="callname">${esc(t.ko)}<code>${esc(c.name)}</code></p>`;
  if (!v) return head + `<p class="dec t-muted">${c.result ? "판정 기록이 없는 호출 · 옛 측정은 읽기 호출을 검증 대상에서 제외" : "검증 중"}</p>` + rawHTML(c);
  const p = v.reasoned || v.direct, d0 = v.reasoned ? v.direct : null;
  const tone = {PASS:"pass", CONFIRM:"ask", BLOCK:"block"}[v.decision] || "";
  const hitQ = c.final ? Q_OF_RULE[v.rule] : null;
  const val = (x, x0) => x0 != null && Math.abs(x0 - x) >= 0.005 ? `<small>${x0.toFixed(2)} → </small>${x.toFixed(2)}` : x.toFixed(2);
  const qs = [];
  if (p){
    const q = (key, ko, x, x0, ticks) => qs.push(`<div class="q${hitQ === key ? " hit " + tone : ""}">
      <span class="ko">${ko}<code>${key}</code></span><span class="val">${val(x, x0)}</span>${meter(x, ticks, x0)}</div>`);
    q("match", "요청 의도 일치도", p.match, d0 && d0.match, [0.2, 0.8]);
    if (p.injected_asked === false) qs.push(`<div class="q"><span class="ko">인젝션 유래 여부<code>injected</code></span><span class="val t-muted">–</span>
      <span class="na">평가 생략 (Skipped) · 이때까지 읽은 외부 컨텍스트 0건</span></div>`);
    else q("injected", "인젝션 유래 여부", p.injected, d0 && d0.injected, [0.2, 0.5, 0.8]);
    q("undo", "가역성 (복구 가능 여부)", p.undo, d0 && d0.undo, [0.8]);
    const gp = p.grade_p || {};
    const gsrc = p.grade_source === "code" ? "모델에 묻지 않고 정적 툴 권한표 (코드)로 결정"
      : ["read", "modify", "send", "delete"].filter(k => gp[k] != null).map(k => `${KIND_KO[k]} ${Number(gp[k]).toFixed(2)}`).join(" · ");
    qs.push(`<div class="q"><span class="ko">작업 위험 등급 (액션 유형)<code>grade</code></span><span class="val" style="font-family:var(--sans)">${esc(KIND_KO[p.grade] || p.grade || "")}</span>
      <span class="na">${esc(gsrc)}</span></div>`);
    for (const r of (v.rules || [])){
      const h = r.hit && /^company rule/.test(v.rule || "");
      qs.push(`<div class="q${h ? " hit ask" : ""}"><span class="ko">사내 정책 위반 여부<code>rule_${esc(r.id)}</code></span><span class="val">${Number(r.p).toFixed(2)}</span>
        ${meter(r.p, [r.threshold])}<span class="na">「${esc(r.text)}」 · ${r.threshold} 이상이면 승인 필요 · 차단·보류 전용 (허용 우회 불가)</span></div>`);
    }
    if (Array.isArray(v.rules_on) && v.rules_on.length && !(v.rules || []).length)
      qs.push(`<div class="q"><span class="ko">사내 정책 위반 여부<code>rule_${esc(v.rules_on[0])}</code></span><span class="val t-muted">–</span>
        <span class="na">평가 생략 (Skipped) · 외부 전송 호출에만 묻는 규칙</span></div>`);
  }
  const noProbs = !p ? `<p class="dec">검증 서버 무응답 · 확률 없이 코드가 결정. 읽기 전용으로 아는 툴만 실행하고 나머지는 보류</p>` : "";
  const lines = POLICY_LINES.filter(l => !l.show || l.show(v)).map(l => {
    const on = v.rule === l.rule || (l.alt && v.rule === l.alt);
    return `<div class="${on ? "on" : ""}"><span>${esc(l.code)}</span><span>${esc(l.out)}</span></div>`;
  }).join("");
  const ms = v.ms || {};
  const facts = [];
  facts.push(["결정", `<b class="t-${tone || "muted"}">${esc(DECISION_KO[v.decision] || v.decision)}</b> <span class="mono t-muted">${esc(v.decision)}</span>` + (o.key !== "pass" && o.key !== "block" && c.final ? ` · ${esc(o.word)}` : "")]);
  if (v.stage) facts.push(["단계", esc(STAGE_KO[v.stage] || v.stage)]);
  if (v.rule) facts.push(["매칭된 규칙", `<span class="mono">${esc(v.rule)}</span>`]);
  if (ms.direct != null) facts.push(["1차 판별 (Direct)", `<span class="mono">${secs(ms.direct)}</span>` + (ms.server_direct != null ? ` <span class="t-muted">(모델 추론 ${secs(ms.server_direct)})</span>` : "")]);
  if (ms.reasoned != null) facts.push(["심층 추론 (Reasoning)", `<span class="mono">${secs(ms.reasoned)}</span>` + (v.reasoning_tokens ? ` · ${esc(v.reasoning_tokens)}토큰` : "") + (v.cut ? ` · <span class="t-block">토큰 한도 초과 (Truncated)</span>` : "")]);
  if (v.policy) facts.push(["정책 버전", `<span class="mono">${esc(v.policy)} ${esc(v.policy_version || "")}</span>`]);
  if (st.worker || st.via) facts.push(["실행 모델", esc(workerName(st)) + (st.via === "mcp" ? " · MCP로 연동" : "")]);
  const reasoning = v.reasoning ? `<details><summary>추론 로그 (CoT / Thinking)</summary><pre>${esc(v.reasoning)}</pre></details>` : "";
  return head + `<p class="dec">${esc(whyWords(v))}</p>
    ${qs.length ? `<h3>독립 평가 지표 (격리 판별 · Zoro-1)</h3>${qs.join("")}` : noProbs}
    <h3>결정론적 정책 코드 (동일 점수 → 동일 판정)</h3><div class="code">${lines}</div>
    <h3>메타데이터</h3><dl class="facts">${facts.map(([k, x]) => `<dt>${k}</dt><dd>${x}</dd>`).join("")}</dl>
    ${reasoning}${rawHTML(c)}`;
}
function rawHTML(c){
  return `<details><summary>Raw Payload (JSON)</summary><pre>${esc(JSON.stringify({name:c.name, args:c.args}, null, 1))}</pre></details>`;
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
