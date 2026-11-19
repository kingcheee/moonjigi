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

// 얇은 선형 인라인 SVG 아이콘 (외부 CDN 없이 사용)
const ICO = {
  shield:`<svg class="ico" viewBox="0 0 24 24"><path d="M12 3l7 3v6c0 4.5-3 7.8-7 9-4-1.2-7-4.5-7-9V6l7-3z"/><path d="M9.5 12.2l1.8 1.8 3.6-3.8"/></svg>`,
  panel:`<svg class="ico" viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M15 4v16"/></svg>`,
  copy:`<svg class="ico" viewBox="0 0 24 24"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>`,
  check:`<svg class="ico" viewBox="0 0 24 24"><path d="M5 12.5l4.2 4.2L19 7"/></svg>`,
  x:`<svg class="ico" viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18"/></svg>`,
  help:`<svg class="ico" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 0 1 4.8.9c0 1.6-2.3 2-2.3 3.4"/><circle cx="12" cy="17.2" r=".7" fill="currentColor" stroke="none"/></svg>`,
  clock:`<svg class="ico" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>`,
  replay:`<svg class="ico" viewBox="0 0 24 24"><path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/></svg>`,
  mail:`<svg class="ico" viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 7l9 6 9-6"/></svg>`,
  file:`<svg class="ico" viewBox="0 0 24 24"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/></svg>`,
  cal:`<svg class="ico" viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 10h18"/></svg>`,
  globe:`<svg class="ico" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a13 13 0 0 1 0 18M12 3a13 13 0 0 0 0 18"/></svg>`,
};
async function copyText(str, btn, resetLabel = "복사"){
  let ok = false;
  try { if (window.isSecureContext && navigator.clipboard){ await navigator.clipboard.writeText(str); ok = true; } } catch (e) {}
  if (!ok){
    const ta = document.createElement("textarea");
    ta.value = str; ta.style.cssText = "position:fixed;opacity:0;pointer-events:none";
    document.body.appendChild(ta); ta.select();
    try { ok = document.execCommand("copy"); } catch (e) {}
    ta.remove();
  }
  if (ok && btn){
    const prev = btn.innerHTML;
    btn.innerHTML = ICO.check + " 복사됨";
    setTimeout(() => { btn.innerHTML = prev || resetLabel; }, 1400);
  }
  return ok;
}
function highlightContextHTML(text){
  const lines = String(text ?? "").split("\n"), normal = [], inj = [];
  for (const ln of lines){
    if (/^\s*(?:※\s*이 메일을 처리하는 AI|--\s*담당 AI 안내)/.test(ln)) inj.push(ln);
    else normal.push(ln);
  }
  let out = esc(normal.join("\n"));
  if (inj.length) out += `<span class="hid"><em>메일 본문 내 인젝션 지시문</em>${esc(inj.join("\n"))}</span>`;
  return out;
}
function highlightPiiHTML(text){
  const safe = esc(text ?? "");
  return safe.replace(/((?:국민|신한|우리|하나|농협|기업|카카오|토스|KB|NH|IBK)?\s*\d{2,4}-\d{2,6}-\d{3,8}(?:\s*(?:\([^)]+\)|[가-힣A-Za-z*]{2,4}))?|\d{6}-[1-4]\d{6})/g,
    `<mark class="pii-mark" title="금융·개인 식별정보">$1</mark>`);
}
function speedBadgeHTML(c){
  const v = c && c.v;
  if (!v) return "";
  if (v.gate_down || v.stage === "failsafe") return `<span class="lat-txt failsafe">안전 보류</span>`;
  const ms = v.ms || {};
  if (ms.reasoned != null) return `<span class="lat-txt reasoned">${secs(ms.reasoned)} · 심층 추론</span>`;
  if (ms.direct != null) return `<span class="lat-txt">${secs(ms.direct)}</span>`;
  if (ms.server_direct != null) return `<span class="lat-txt">${secs(ms.server_direct)}</span>`;
  return "";
}

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
  if (truthy(a.recursive)) s += " · 하위 폴더 포함";
  if (truthy(a.permanent)) s += " · 영구 삭제";
  return s;
}
// kind: read 읽기 전용 · modify 수정 / 변경 · send 외부 전송 · delete 삭제 (gate.py의 grade와 같은 낱말)
const TOOLS = {
  list_mail:    {kind:"read",   ko:"메일 목록 조회",    what: a => ""},
  read_mail:    {kind:"read",   ko:"메일 조회",         what: (a, names) => (names && names[a.id]) || a.id || ""},
  search_files: {kind:"read",   ko:"파일 검색",         what: a => `「${a.query ?? ""}」`},
  read_doc:     {kind:"read",   ko:"문서 조회",         what: a => baseName(a.path)},
  fetch_url:    {kind:"read",   ko:"웹페이지 조회",     what: a => a.url ?? ""},
  list_events:  {kind:"read",   ko:"일정 조회",         what: a => a.date ?? ""},
  move_file:    {kind:"modify", ko:"파일 이동",         what: a => `${baseName(a.path)} → ${a.to ?? ""}`},
  create_event: {kind:"modify", ko:"일정 생성",         what: a => [a.title, whenKo(a.start, a.end)].filter(Boolean).join(" · ")},
  send_email:   {kind:"send",   ko:"메일 발송",         what: a => a.to ?? ""},
  share_link:   {kind:"send",   ko:"공유 링크 생성",    what: a => baseName(a.path) + (truthy(a.public) ? " · 전체 공개" : "")},
  delete_file:  {kind:"delete", ko:"파일 삭제",         what: a => deleteTarget(a)},
  delete_mail:  {kind:"delete", ko:"메일 삭제",         what: a => deleteTarget(a)},
};
const KIND_KO = {read:"읽기 전용", modify:"수정 / 변경", send:"외부 전송", delete:"삭제"};
function toolOf(name){ return TOOLS[name] || {kind:null, ko:name, what: a => { try { return JSON.stringify(a); } catch (e) { return ""; } }}; }
function kindOf(c){
  const t = TOOLS[c.name];
  if (t) return t.kind;
  const p = c.v && (c.v.reasoned || c.v.direct);
  return (p && p.grade) || (c.v && c.v.effect) || null;
}

// ───────────── 4. 판정을 사람 말로 ─────────────
function isHeld(cf){ return /^mcp/.test(cf.by || "") || /^mcp:/.test(cf.note || ""); }   // 외부 에이전트(MCP): 승인 채널 미연결로 보류
// 호출 하나가 지금 어떤 상태인가 → {key, word(짧은 말), tone(pass|ask|block|muted)}
function outcome(c, S){
  const v = c.v;
  if (!v){
    if (c.result) return {key:"none", word:"읽기 · 통과", tone:"muted"};        // 옛 기록: 부작용 없는 호출은 검증 생략
    return {key:"checking", word:"검증 중", tone:"muted"};
  }
  if (v.decision === "REASON" && !c.final) return {key:"thinking", word:"심층 추론 중", tone:"ask"};
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
// 매칭된 규칙(verdict.rule) → 사용자 쪽에서 본 이유. [짧은 말, 덧붙일 말]
function whyParts(v){
  const r = (v && v.rule) || "";
  if (/^company rule/.test(r)){
    const hit = (v.rules || []).find(x => x.hit);
    return ["사내 정책 위반", "「" + (hit ? hit.text : "사내 정책") + "」"];
  }
  if (r === "risky & match<=0.2") return ["요청하지 않은 작업", ""];
  if (r === "risky & injected>=0.8") return ["프롬프트 인젝션 감지", "사용자 요청이 아니라 읽은 문서 속 숨겨진 지시에서 나온 작업입니다"];
  if (/^gate unreachable: held/.test(r)) return ["검증 서버 무응답", "안전상 읽기 전용 외 작업은 보류합니다"];
  if (/^gate unreachable: known/.test(r)) return ["검증 서버 무응답", "읽기 전용 작업이라 그대로 통과했습니다"];
  if (/^gate error/.test(r)) return ["검증 서버 연결 실패", "안전상 실행을 중단했습니다"];
  if (/cut\/timeout/.test(r)) return ["추론 시간 초과", "되돌릴 수 없는 작업이라 사람 확인이 필요합니다"];
  if (r === "still unsure & risky" || /^risky & unsure/.test(r)) return ["확신 부족", "위반 규칙은 없지만 되돌릴 수 없는 작업입니다"];
  if (r === "still unsure & safe") return ["확신 부족", "외부 전송·삭제가 아닌 작업이라 통과했습니다"];
  if (r === "known read-only tool" || r === "read & injected<0.5") return ["읽기 전용", ""];
  if (/^match>=0\.8/.test(r)) return ["정상 요청", "외부 지시(인젝션)와 무관한 작업입니다"];
  if (r === "no rule fired") return ["추가 추론 필요", ""];
  return [r, ""];
}
function whyWords(v){ return whyParts(v).filter(Boolean).join(" · "); }        // 한 줄로 이은 것(「판별 상세」· 콘솔이 쓴다)
const DECISION_KO = {PASS:"통과", REASON:"심층 추론", CONFIRM:"승인 필요", BLOCK:"차단"};
const STAGE_KO = {direct:"1차 판별", reasoned:"심층 추론 후 판정", human:"심층 추론 후 승인 요청", failsafe:"검증 서버 무응답 (안전 보류)"};
const secs = ms => (ms / 1000).toFixed(ms < 995 ? 2 : 1) + "초";

// ───────────── 5. 호출 예정 툴 실물 ─────────────
const hasBatchim = s => { const ch = String(s || "").trim().slice(-1).charCodeAt(0); return ch >= 0xAC00 && ch <= 0xD7A3 && ((ch - 0xAC00) % 28) !== 0; };
const eul = s => hasBatchim(s) ? "을" : "를";
const ira = s => hasBatchim(s) ? "이라" : "라";
function actionNoun(c){
  const a = c.args || {};
  if (c.name === "delete_file"){
    if (String(a.path || "") === ".") return "폴더 전체 삭제";
    if (truthy(a.recursive) || /\*/.test(String(a.path || ""))) return "폴더 삭제";
    return "파일 삭제";
  }
  if (c.name === "delete_mail") return "메일 삭제";
  if (c.name === "send_email") return "메일 발송";
  if (c.name === "share_link") return truthy(a.public) ? "전체 공개 링크 공유" : "링크 공유";
  return toolOf(c.name).ko;
}
function storyForCall(c, S, o){
  const v = c.v || {}, r = v.rule || "", act = actionNoun(c);
  const task = (S && S.start && S.start.task) || "";
  const askLead = task ? `「${task}」만 요청했지만, ` : "";
  if (o.key === "block"){
    if (r === "risky & injected>=0.8")
      return [`숨겨진 악성 지시에 속은 ${act} 시도를 멈췄습니다`,
        `에이전트가 읽은 문서 속 숨겨진 지시에 속아 ${act}${eul(act)} 시도했지만, 실행 직전에 문지기가 차단했습니다.`];
    if (r === "risky & match<=0.2"){
      const isRoot = c.name === "delete_file" && String((c.args || {}).path || "") === ".";
      const tgt = c.name === "delete_file" && !isRoot ? deleteTarget(c.args || {}) : "";
      const desc = isRoot ? `현재 폴더 전체${truthy((c.args || {}).recursive) ? "(하위 폴더 포함)" : ""} 삭제를`
        : `${tgt ? `「${tgt}」 ` : ""}${act}${eul(act)}`;
      return [`요청하지 않은 ${act} 시도를 실행 직전에 멈췄습니다`,
        `${askLead}에이전트가 요청과 무관하게 ${desc} 시도해 문지기가 차단했습니다.`];
    }
    return [`위험한 ${act} 시도를 실행 직전에 멈췄습니다`, `문지기 정책에 따라 ${act}${eul(act)} 차단했습니다.`];
  }
  if (o.key === "held"){
    if (/^company rule/.test(r))
      return [`금융·개인정보가 포함된 외부 에이전트의 ${act}${eul(act)} 보류했습니다`,
        `사내 정책(계좌번호·주민등록번호 사외 유출 금지)에 걸렸으며, 외부 에이전트 요청이라 바로 승인할 수 없어 발송을 멈춰 두었습니다.`];
    if (/^gate unreachable/.test(r))
      return [`검증 서버가 중단돼도 안전을 위해 ${act}${eul(act)} 멈춰 두었습니다`,
        `검증 서버가 응답하지 않는 장애 상황에서는 읽기 작업만 허용하고, ${act} 같은 위험 작업은 자동으로 보류합니다.`];
    return [`확인이 필요한 외부 에이전트의 ${act}${eul(act)} 보류했습니다`,
      `외부 에이전트 요청이라 바로 승인할 수 없어 실행을 멈춰 두었습니다.`];
  }
  if (["asking", "declined", "expired", "unanswered"].includes(o.key)){
    if (/^company rule/.test(r)){
      const hit = (v.rules || []).find(x => x.hit);
      return [`금융·개인정보가 포함된 ${act}${eul(act)} 멈추고 승인을 요청했습니다`,
        `사내 정책(「${hit ? hit.text : "사내 정책"}」)에 걸려 실행 직전에 멈췄습니다.`];
    }
    if (/cut\/timeout/.test(r))
      return [`추론 시간이 초과된 ${act}${eul(act)} 멈추고 확인을 요청했습니다`,
        `되돌릴 수 없는 작업이라 자동 통과시키지 않고 실행을 멈췄습니다.`];
    if (/^gate unreachable/.test(r))
      return [`검증 서버가 중단돼 안전을 위해 ${act}${eul(act)} 멈춰 두었습니다`,
        `검증 서버가 응답하지 않을 때는 위험 작업을 실행하지 않고 보류합니다.`];
    return [`되돌릴 수 없는 ${act}${ira(act)} 실행 전 멈추고 확인을 요청했습니다`,
      `명확한 규칙 위반은 아니지만 안전하다고 확신할 수 없어, 실행 전에 문지기가 멈추고 사람 확인을 요청했습니다.`];
  }
  if (o.key === "approved")
    return [`사람 승인 후 ${act}${eul(act)} 실행했습니다`, `승인이 완료되어 요청된 작업을 진행했습니다.`];
  if (o.key === "pass")
    return [`정상 요청으로 확인되어 ${act}${eul(act)} 통과시켰습니다`, `사용자 요청과 일치하고 숨겨진 악성 지시와 무관한 안전한 작업입니다.`];
  return ["", ""];
}
function storyForBulk(calls, S, blocked, pending){
  const n = calls.length, isMail = calls[0].name === "delete_mail";
  const unit = isMail ? "메일" : "파일", cnt = isMail ? `${n}통` : `${n}개`;
  const task = (S && S.start && S.start.task) || "";
  if (blocked === n)
    return [`${unit} ${cnt} 무단 삭제 시도를 모두 멈췄습니다`,
      task ? `「${task}」만 요청했지만, 에이전트가 오작동으로 ${unit} ${cnt}${eul(cnt)} 연달아 지우려 해 문지기가 실행 직전에 전부 차단했습니다.`
        : `에이전트가 요청하지 않은 ${unit} ${cnt} 삭제를 연달아 시도해 문지기가 실행 직전에 전부 차단했습니다.`];
  if (blocked && pending)
    return [`${unit} 무단 삭제 시도를 실시간으로 막고 있습니다 (${blocked}/${n}건 차단)`,
      `요청하지 않은 ${unit} 삭제 호출이 연달아 발생해 문지기가 건마다 차단하는 중입니다.`];
  if (blocked)
    return [`${unit} 삭제 ${n}건 중 ${blocked}건을 차단했습니다`,
      `요청 범위를 벗어난 삭제 시도를 실행 직전에 멈췄습니다.`];
  return [pending ? `${unit} 삭제 요청을 검증하는 중입니다` : `${unit} 삭제 ${n}건 검증을 마쳤습니다`, ""];
}

// 결정 띠 — 실물 아래에 찍힌다. 굵은 볼드 고딕 헤드라인으로 어떤 오작동/위험을 멈췄는지 한눈에 설명.
const ASK_Q = {send:"이 메일 발송을 승인할까요?", share:"이 링크 공유를 승인할까요?", delete:"이 삭제를 승인할까요?", other:"이 작업을 승인할까요?"};
function rulingHTML(c, S, live, tryMode){
  const o = outcome(c, S), v = c.v;
  const ms = (v && v.ms) || {};
  const peek = `<button type="button" class="linkish" data-peek="${esc(c.id)}">판별 상세</button>`;
  if (o.key === "checking") return `<div class="ruling"><p class="h pulse">검증 중…</p></div>`;
  if (o.key === "none") return `<div class="ruling"><p class="sub">읽기 작업 · 별도 검증 없이 통과</p></div>`;
  if (o.key === "thinking")
    return `<div class="ruling ask"><p class="h">심층 추론 중 <span class="mono" data-timer="${esc(c.id)}"></span></p>
      <p class="headline">안전 여부를 한 번 더 깊게 따져 보고 있습니다</p>
      <p class="explain">1차 판별만으로 확신하기 어려워 추론 과정을 거쳐 재판별하는 중입니다.</p></div>`;
  const [short] = whyParts(v);
  const [headline, explain] = storyForCall(c, S, o);
  const word = o.key === "pass" ? "통과" : o.key === "block" ? "차단" : o.key === "held" ? "보류" : "승인 필요";
  const kind = kindOf(c), q = ASK_Q[kind === "send" ? (c.name === "send_email" ? "send" : "share") : kind === "delete" ? "delete" : "other"];
  let sub = "", act = "", bar = "";
  switch (o.key){
    case "asking":
      sub = q;
      if (live){
        act = `<button type="button" class="b hitl-deny" data-answer="no">${ICO.x} 거절 <kbd>N</kbd></button>
          <button type="button" class="b hitl-approve" data-answer="yes">${ICO.check} 승인하고 실행 <kbd>Y</kbd></button>
          <span class="left" data-countdown></span>`;
        bar = `<div class="cdbar" aria-hidden="true"><i data-countdown-bar style="width:100%"></i></div>`;
      }
      break;
    case "approved":   sub = "승인됨 · 실행 완료"; break;
    case "declined":   sub = "거절됨 · 실행 중단"; break;
    case "expired":    sub = "시간 초과 · 실행 중단"; break;
    case "held":       sub = ""; break;
    case "unanswered": sub = tryMode ? "실제 실행 시 여기서 사람 승인을 기다립니다" : "저장된 시연 기록 · 승인 없이 실행 중단"; break;
  }
  const lat = speedBadgeHTML(c);
  const thought = ms.reasoned != null ? `<p class="sub">${secs(ms.reasoned)} 심층 추론 결과${sub ? " · " + sub : ""}</p>` : (sub ? `<p class="sub">${sub}</p>` : "");
  return `<div class="ruling ${o.tone}"><div class="ruling-top"><p class="h">${word}${short ? " · " + esc(short) : ""}</p>${lat}</div>
    ${headline ? `<p class="headline">${esc(headline)}</p>` : ""}
    ${explain ? `<p class="explain">${esc(explain)}</p>` : ""}${thought}${bar}
    <div class="act">${act}<span class="grow"></span>${peek}</div></div>`;
}
const THING_HEAD = {send:["에이전트가 발송하려는 메일", "에이전트가 발송하려던 메일", "에이전트가 발송한 메일"], del:["에이전트가 삭제하려는 항목", "에이전트가 삭제하려던 항목", "에이전트가 삭제한 항목"],
  other:["호출 예정 툴", "호출하려던 툴", "실행된 툴"]};
function tense(o){ return ["pass", "approved"].includes(o.key) ? 2 : (["checking", "thinking", "asking"].includes(o.key) ? 0 : 1); }

// 메일 초안
function mailThingHTML(c, S, live){
  const a = c.args, o = outcome(c, S);
  const att = Array.isArray(a.attach) && a.attach.length ? `<dt>첨부파일</dt><dd>${a.attach.map(x => esc(baseName(x))).join(", ")}</dd>` : "";
  const bodyHTML = highlightPiiHTML(a.body || "");
  return `<article class="thing" data-call="${esc(c.id)}">
    <p class="thing-h"><span>${THING_HEAD.send[tense(o)]}</span></p>
    <dl class="mailhead"><dt>받는 사람</dt><dd>${esc(a.to || "")}</dd>${a.subject ? `<dt>제목</dt><dd>${esc(a.subject)}</dd>` : ""}${att}</dl>
    <div class="mailbody">${bodyHTML}</div>
    ${rulingHTML(c, S, live)}</article>`;
}
// 삭제 항목 — 같은 툴을 잇달아 부르면 한 목록으로 묶는다
function bulkThingHTML(calls, S, live){
  const os = calls.map(c => outcome(c, S));
  const n = calls.length;
  const rows = calls.map((c, i) => `<li data-peek="${esc(c.id)}"><span>${esc(deleteTarget(c.args))}</span><span class="t-${os[i].tone}">${esc(os[i].word)}</span></li>`).join("");
  if (n === 1){
    return `<article class="thing" data-call="${esc(calls[0].id)}"><p class="thing-h"><span>${THING_HEAD.del[tense(os[0])]}</span></p>
      <ul class="bulk one"><li data-peek="${esc(calls[0].id)}"><span>${esc(deleteTarget(calls[0].args))}</span><span></span></li></ul>
      ${rulingHTML(calls[0], S, live)}</article>`;
  }
  const count = k => os.filter(o => o.key === k).length;
  const blocked = count("block"), executed = calls.filter(c => c.executed === true).length;
  const pending = os.filter(o => ["checking", "thinking"].includes(o.key)).length;
  const rules = [...new Set(calls.filter((c, i) => os[i].key === "block").map(c => c.v.rule))];
  let h, tone = "block";
  const one = rules.length === 1 ? " · " + esc(whyParts({rule:rules[0]})[0]) : "";
  if (blocked === n) h = `차단 ${n}건${one}`;
  else if (blocked && blocked + pending === n) h = `차단 ${blocked}건${one} <span class="pulse">· 검증 중…</span>`;
  else if (blocked) h = `${n}건 중 차단 ${blocked}건${one}`;
  else { h = pending ? "검증 중…" : "건별 검증 완료"; tone = pending ? "" : "ask"; }
  const why = rules.length > 1 ? `<p class="sub">항목별 다른 사유 · 항목을 클릭하면 판별 상세 표시</p>` : "";
  const [headline, explain] = storyForBulk(calls, S, blocked, pending);
  const last = calls[n - 1];
  return `<article class="thing"><p class="thing-h"><span>에이전트가 삭제하려던 항목 · ${n}건</span><span class="bulk-stat">차단 <b>${blocked}/${n}</b> · 삭제 <b>${executed}건</b></span></p>
    <ol class="bulk">${rows}</ol>
    <div class="ruling ${tone}"><div class="ruling-top"><p class="h">${h}</p>${speedBadgeHTML(last)}</div>
      ${headline ? `<p class="headline">${esc(headline)}</p>` : ""}
      ${explain ? `<p class="explain">${esc(explain)}</p>` : ""}${why}
      <div class="act"><span class="grow"></span><button type="button" class="linkish" data-peek="${esc(last.id)}">판별 상세</button></div></div></article>`;
}
// 그 밖의 툴(공유 링크 등)
function otherThingHTML(c, S, live){
  const o = outcome(c, S), t = toolOf(c.name);
  const rows = Object.entries(c.args).map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(typeof v === "string" ? v : JSON.stringify(v))}</dd>`).join("");
  return `<article class="thing" data-call="${esc(c.id)}"><p class="thing-h"><span>${THING_HEAD.other[tense(o)]} · ${esc(t.ko)}</span></p>
    <dl class="argsdl">${rows}</dl>${rulingHTML(c, S, live)}</article>`;
}

// ───────────── 6. 판별 상세 ─────────────
// 정책 코드 — gate.py의 policy()·policy_v2()·v3 계열을 그대로 옮겼다(viewer.html과 같은 목록). verdict.rule로 매칭된 규칙을 고른다.
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
// 매칭된 규칙이 어느 지표 때문인가
const Q_OF_RULE = {"risky & injected>=0.8":"injected", "risky & match<=0.2":"match"};

function meter(p, ticks, ghost){
  const tk = (ticks || []).map(x => `<u style="left:${x * 100}%"></u>`).join("");
  const g = ghost != null ? `<s style="left:calc(${ghost * 100}% - 1px)" title="1차 판별값 ${ghost.toFixed(2)}"></s>` : "";
  return `<div class="meter"><i style="width:${Math.max(0, Math.min(1, p)) * 100}%"></i>${tk}${g}</div>`;
}
function insideHTML(c, S){
  const v = c.v, st = (S && S.start) || {}, t = toolOf(c.name), o = outcome(c, S);
  const head = `<p class="callname">${esc(t.ko)}<code>${esc(c.name)}</code></p>`;
  if (!v) return head + `<p class="dec t-muted">${c.result ? "읽기 전용 작업은 별도 검증 없이 바로 통과했습니다" : "검증 중"}</p>` + rawHTML(c);
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
      <span class="na">해당 없음 · 이전에 조회한 외부 문서 없음</span></div>`);
    else q("injected", "인젝션 유래 여부", p.injected, d0 && d0.injected, [0.2, 0.5, 0.8]);
    q("undo", "복구 가능 여부", p.undo, d0 && d0.undo, [0.8]);
    const gp = p.grade_p || {};
    const gsrc = p.grade_source === "code" ? "툴 권한표로 자동 분류"
      : ["read", "modify", "send", "delete"].filter(k => gp[k] != null).map(k => `${KIND_KO[k]} ${Number(gp[k]).toFixed(2)}`).join(" · ");
    qs.push(`<div class="q"><span class="ko">작업 유형<code>grade</code></span><span class="val" style="font-family:var(--sans)">${esc(KIND_KO[p.grade] || p.grade || "")}</span>
      <span class="na">${esc(gsrc)}</span></div>`);
    for (const r of (v.rules || [])){
      const h = r.hit && /^company rule/.test(v.rule || "");
      qs.push(`<div class="q${h ? " hit ask" : ""}"><span class="ko">사내 정책 위반 여부<code>rule_${esc(r.id)}</code></span><span class="val">${Number(r.p).toFixed(2)}</span>
        ${meter(r.p, [r.threshold])}<span class="na">기준 ${r.threshold} 이상이면 승인 요청</span></div>`);
    }
    if (Array.isArray(v.rules_on) && v.rules_on.length && !(v.rules || []).length)
      qs.push(`<div class="q"><span class="ko">사내 정책 위반 여부<code>rule_${esc(v.rules_on[0])}</code></span><span class="val t-muted">–</span>
        <span class="na">해당 없음 · 외부 전송 작업에만 적용</span></div>`);
  }
  const noProbs = !p ? `<p class="dec">검증 서버가 응답하지 않아 읽기 전용 작업만 통과하고 나머지는 보류했습니다</p>` : "";
  const lines = POLICY_LINES.filter(l => !l.show || l.show(v)).map(l => {
    const on = v.rule === l.rule || (l.alt && v.rule === l.alt);
    return `<div class="${on ? "on" : ""}"><span>${esc(l.code)}</span><span>${esc(l.out)}</span></div>`;
  }).join("");
  const ms = v.ms || {};
  const facts = [];
  facts.push(["결정", `<b class="t-${tone || "muted"}">${esc(DECISION_KO[v.decision] || v.decision)}</b> <span class="mono t-muted">${esc(v.decision)}</span>` + (o.key !== "pass" && o.key !== "block" && c.final ? ` · ${esc(o.word)}` : "")]);
  if (v.stage) facts.push(["단계", esc(STAGE_KO[v.stage] || v.stage)]);
  if (v.rule) facts.push(["매칭된 규칙", `<span class="mono">${esc(v.rule)}</span>`]);
  if (ms.direct != null) facts.push(["1차 판별", `<span class="mono">${secs(ms.direct)}</span>` + (ms.server_direct != null ? ` <span class="t-muted">(모델 ${secs(ms.server_direct)})</span>` : "")]);
  if (ms.reasoned != null) facts.push(["심층 추론", `<span class="mono">${secs(ms.reasoned)}</span>` + (v.reasoning_tokens ? ` · ${esc(v.reasoning_tokens)}토큰` : "") + (v.cut ? ` · <span class="t-muted">토큰 한도 초과</span>` : "")]);
  if (v.policy) facts.push(["정책 버전", `<span class="mono">${esc(v.policy)} ${esc(v.policy_version || "")}</span>`]);
  if (st.worker || st.via) facts.push(["실행 모델", esc(workerName(st)) + (st.via === "mcp" ? " · MCP" : "")]);
  const reasoning = v.reasoning ? `<details><summary>추론 과정 보기</summary><pre>${esc(v.reasoning)}</pre></details>` : "";
  return head + `<p class="dec">${esc(whyWords(v))}</p>
    ${qs.length ? `<h3>평가 지표 · Zoro-1</h3>${qs.join("")}` : noProbs}
    <h3>정책 코드</h3><div class="code">${lines}</div>
    <h3>실행 정보</h3><dl class="facts">${facts.map(([k, x]) => `<dt>${k}</dt><dd>${x}</dd>`).join("")}</dl>
    ${reasoning}${rawHTML(c)}`;
}
function rawHTML(c){
  return `<details><summary>호출 원문 (JSON)</summary><pre>${esc(JSON.stringify({name:c.name, args:c.args}, null, 1))}</pre></details>`;
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
