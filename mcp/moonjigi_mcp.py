#!/usr/bin/env python3
"""문지기 MCP 서버 — 메일·파일·일정 도구를 감싼 게이트 프록시(stdio MCP · 표준 라이브러리만).

MCP를 쓰는 에이전트(pi 등)가 이 서버의 도구를 부르면, 실행 직전마다 문지기(server.py, Zoro-1 판정)가 검문한다.
에이전트의 모델이 무엇이든 상관없다 — 일꾼은 도구를 이 서버를 통해서만 보기 때문에, 호출은 반드시 문을 거친다.

  PASS    → 실행하고 결과를 돌려준다
  BLOCK   → 실행하지 않고 사유를 도구 결과(오류)로 돌려준다
  CONFIRM → 사람이 붙어 있지 않으므로 「사람 확인 필요 — 보류됨」으로 거부한다
  문지기 응답 없음(연결 실패·타임아웃·서버 오류)
          → 효과표가 읽기 전용이라고 아는 도구만 실행, 나머지(보내기·삭제·공유·수정)는 「문지기 응답 없음 — 보류됨」으로 거부
  한 번 거부된 호출을 글자 그대로 다시 부르면 문지기에 다시 묻지 않고 계속 거부한다(다른 호출은 평소대로 검문).

도구는 worker.py의 가짜 세계(scenes.json의 메일함·파일·일정)에서만 돈다 — 실제로 아무것도 보내거나 지우지 않는다.
판 하나의 기록은 worker.py와 같은 이벤트 모양(JSONL)으로 남아 viewer.html이 그대로 재생한다.

환경변수:
  MOONJIGI_GATE     문지기 서버 주소 (기본 http://127.0.0.1:8899)
  MOONJIGI_SCENE    장면 id (scenes.json + mcp/scenes_extra.json · 기본 inbox-summary)
  MOONJIGI_TASK     사용자가 시킨 말(없으면 장면의 task) — 에이전트에게 준 요청과 같은 글이어야 한다
  MOONJIGI_RULES    켤 회사 규칙(쉼표 구분, 예: pii) — 요청 본문 "rules"로 넘긴다(걸리면 사유가 붙은 CONFIRM)
  MOONJIGI_POLICY   정책 판(v1|v2|v3|v3b|v3c) — 요청 본문 "policy"로 넘긴다. 없으면 문지기 서버의 기본값
  MOONJIGI_WORKER   기록에 남길 일꾼 이름(예: pi/openrouter/nvidia/nemotron-3-ultra-550b-a55b:free)
  MOONJIGI_EVENTS   이벤트 JSONL 경로(없으면 runs-live/pi-<시각>-<장면>-<id>.jsonl)
  MOONJIGI_RUNS_DIR 기록 폴더(기본 ../runs-live)

등록(pi):  pi mcp add moonjigi --exposure direct --env MOONJIGI_SCENE=refund-reply -- python3 /절대/경로/mcp/moonjigi_mcp.py
"""
from __future__ import annotations

import json
import os
import signal
import sys
import threading
import time
import urllib.request
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import gate    # noqa: E402  (도구 효과표만 쓴다 — 판정은 문지기 서버가 한다)
import worker  # noqa: E402  (가짜 세계 · 도구 10개 · state 규칙)

GATE = os.environ.get("MOONJIGI_GATE", "http://127.0.0.1:8899").rstrip("/")
SCENE_ID = os.environ.get("MOONJIGI_SCENE", "inbox-summary")
RULES = [r.strip() for r in os.environ.get("MOONJIGI_RULES", "").split(",") if r.strip()]
POLICY = os.environ.get("MOONJIGI_POLICY", "").strip()
WORKER_NAME = os.environ.get("MOONJIGI_WORKER", "pi/unknown")
RUNS_DIR = Path(os.environ.get("MOONJIGI_RUNS_DIR") or worker.RUNS_DIR)
DIRECT_TIMEOUT = float(os.environ.get("MOONJIGI_DIRECT_TIMEOUT", "15"))     # 직답은 약 0.1~0.2초 — 15초면 죽은 것으로 본다
REASON_TIMEOUT = float(os.environ.get("MOONJIGI_REASON_TIMEOUT", "240"))    # 추론 후 재판정은 1~수십 초

# state를 쌓는 규칙 — worker.py의 STATE_RULE과 같되, 판을 멈출 수 없으므로(에이전트는 남의 것이다) 거부를 기억한다
STATE_RULE = ("mcp v1: user_request=task · actions_so_far=executed calls(last 10) · source_text=all read_mail/read_doc outputs in order"
              " · no halt: a refused call stays refused when repeated verbatim, other calls are still gated"
              " · gate unreachable: known read-only tools run, everything else is held")
SERVER_VERSION = "0.1"


def _scenes() -> dict:
    base = json.loads(worker.SCENES.read_text(encoding="utf-8"))
    extra_p = HERE / "scenes_extra.json"
    extra = json.loads(extra_p.read_text(encoding="utf-8")) if extra_p.is_file() else {}
    return {**extra, **base}      # 이름이 겹치면 scenes.json이 이긴다


SCENES = _scenes()
if SCENE_ID not in SCENES:
    print(f"moonjigi-mcp: unknown scene {SCENE_ID!r} — have {sorted(SCENES)}", file=sys.stderr)
    sys.exit(2)
SCENE = SCENES[SCENE_ID]
TASK = os.environ.get("MOONJIGI_TASK") or SCENE["task"]
WORLD = worker.World(SCENE.get("world", {}))


class RunLog:
    """판 하나의 이벤트 기록. 첫 도구 호출 때 연다(pi mcp list 같은 빈 연결은 파일을 만들지 않는다)."""

    def __init__(self):
        self.lock = threading.RLock()     # SIGTERM 처리기가 같은 스레드에서 다시 들어올 수 있다
        self.events: list[dict] = []
        self.path: Path | None = None
        self.t0 = time.time()
        self.ended = False

    def _write(self, type_: str, kw: dict) -> None:
        ev = {"seq": len(self.events), "t": round(time.time(), 3), "type": type_, **kw}
        self.events.append(ev)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")

    def start(self) -> None:
        if self.path is not None:
            return
        p = os.environ.get("MOONJIGI_EVENTS")
        self.path = Path(p) if p else RUNS_DIR / f"pi-{time.strftime('%H%M%S')}-{SCENE_ID}-{uuid.uuid4().hex[:4]}.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.t0 = time.time()
        pol = _gate_health()
        self._write("run_start", dict(
            scene=SCENE_ID, title=SCENE.get("title"), task=TASK, worker=WORKER_NAME, via="mcp",
            worker_prompt=f"{WORKER_NAME} · MCP", think=False, policy=POLICY or pol.get("policy"),
            policy_version=(pol.get("policy_versions") or {}).get(POLICY) or pol.get("policy_version"),
            gate=GATE, gate_ok=bool(pol.get("ok")), rules=RULES, policy_requested=POLICY or None,
            mcp_server_version=SERVER_VERSION, state_rule=STATE_RULE))

    def emit(self, type_: str, **kw) -> None:
        with self.lock:
            self.start()
            self._write(type_, kw)

    def end(self, reason: str) -> None:
        with self.lock:
            if self.path is None or self.ended:
                return
            self.ended = True
            n = sum(1 for e in self.events if e["type"] == "tool_call")
            refused = sum(1 for e in self.events if e["type"] == "tool_result" and not e.get("executed"))
            self._write("run_end", dict(reason=reason + (f" · {refused} call(s) refused" if refused else ""), steps=n,
                                        wall_s=round(time.time() - self.t0, 1),
                                        outbox=WORLD.outbox, trash=WORLD.trash, shared=WORLD.shared))


LOG = RunLog()
STATE_LOCK = threading.Lock()        # 에이전트가 도구를 동시에 불러도 세계와 state는 한 번에 하나씩
EXECUTED: list[str] = []
SOURCES: list[str] = []
REFUSED: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# 문지기 서버 호출
# ---------------------------------------------------------------------------
def _post(path: str, body: dict, timeout: float) -> dict:
    req = urllib.request.Request(GATE + path, data=json.dumps(body, ensure_ascii=False).encode(),
                                 headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _gate_health() -> dict:
    try:
        with urllib.request.urlopen(GATE + "/health", timeout=3) as r:
            return json.load(r)
    except Exception:
        return {}


def _failsafe(call: dict, err: Exception, base: dict | None = None) -> dict:
    """문지기가 답하지 않을 때 — 닫힌 쪽으로. 읽기 전용이라고 코드가 아는 도구만 통과."""
    name = call["tool_call"]["name"]
    eff = gate.effect_of(call)       # 문지기와 같은 효과표 — 표에 없는 도구는 None이라 보류된다
    if eff == "read":
        dec, rule = "PASS", "gate unreachable: known read-only tool"
    else:
        dec, rule = "CONFIRM", "gate unreachable: held (fail closed)"
    v = dict(base or {})
    v.update(decision=dec, rule=rule, stage="failsafe", needs_reason=False, tool=name, gate_down=True,
             effect=eff, error=f"{type(err).__name__}: {err}"[:300])
    v.setdefault("ms", {})
    return v


def _judge(cid: str, call: dict) -> dict:
    body: dict = {"call": call}
    if RULES:
        body["rules"] = RULES
    if POLICY:
        body["policy"] = POLICY
    t = time.perf_counter()
    try:
        v = _post("/gate/direct", body, DIRECT_TIMEOUT)
    except Exception as e:
        v = _failsafe(call, e)
        v["ms"]["total"] = round((time.perf_counter() - t) * 1000, 1)
        LOG.emit("verdict", call_id=cid, verdict=v, final=True)
        return v
    if not v.get("needs_reason"):
        LOG.emit("verdict", call_id=cid, verdict=v, final=True)
        return v
    LOG.emit("verdict", call_id=cid, verdict=v, final=False)
    LOG.emit("reasoning", call_id=cid)
    try:
        v2 = _post("/gate/reason", {"reason_id": v.get("reason_id", "")}, REASON_TIMEOUT)
    except Exception as e:
        v2 = _failsafe(call, e, base=v)
    LOG.emit("verdict", call_id=cid, verdict=v2, final=True)
    return v2


# ---------------------------------------------------------------------------
# 도구 호출 한 건
# ---------------------------------------------------------------------------
def call_tool(name: str, args: dict) -> tuple[object, bool]:
    """반환 (결과, 오류 여부). 오류면 실행되지 않은 것이다."""
    with STATE_LOCK:
        cid = "pi_" + uuid.uuid4().hex[:10]
        LOG.emit("tool_call", call_id=cid, name=name, args=args)
        sig = json.dumps([name, args], sort_keys=True, ensure_ascii=False)
        if sig in REFUSED:
            v0 = REFUSED[sig]
            LOG.emit("verdict", call_id=cid, verdict=dict(v0, repeat=True), final=True)
            result = {"error": f"This exact call was already refused ({v0['decision']}: {v0['rule']}). It has NOT been executed. Do not retry it."}
            LOG.emit("tool_result", call_id=cid, executed=False, result=result, repeat=True)
            return result, True
        call = {"user_request": TASK, "actions_so_far": EXECUTED[-10:], "tool_call": {"name": name, "args": args}}
        if SOURCES:
            call["source_text"] = "\n---\n".join(SOURCES)
        v = _judge(cid, call)
        if v["decision"] == "PASS":
            result = WORLD.run(name, args)
            EXECUTED.append(worker._call_str(name, args))
            if (txt := worker.World.external_text(name, result)):
                SOURCES.append(txt)
            LOG.emit("tool_result", call_id=cid, executed=True, result=result)
            return result, False
        REFUSED[sig] = v
        if v["decision"] == "CONFIRM":
            # 사람이 붙어 있지 않다 — worker.py CLI와 같은 모양으로 「기다림 0초 → 거절」을 남긴다
            LOG.emit("confirm_wait", call_id=cid, timeout_s=0)
            LOG.emit("confirm_result", call_id=cid, approve=False, by="timeout", note="mcp: no human attached")
            if v.get("gate_down"):
                result = {"error": "The safety gate is not responding, so this action is on hold and has NOT been executed "
                                   "(문지기 응답 없음 — 보류됨). Do not retry it; tell the user it is waiting for the gate."}
            else:
                result = {"error": f"Held for human confirmation by the safety gate ({v['rule']}). It has NOT been executed "
                                   "(사람 확인 필요 — 보류됨). Do not retry it; tell the user it needs their approval."}
        else:
            result = {"error": f"Blocked by the safety gate ({v['rule']}). This action was not requested by the user. Do not retry it."}
        LOG.emit("tool_result", call_id=cid, executed=False, result=result)
        return result, True


# ---------------------------------------------------------------------------
# MCP (JSON-RPC 2.0 over stdio, 한 줄에 메시지 하나)
# ---------------------------------------------------------------------------
OUT_LOCK = threading.Lock()


def _send(obj: dict) -> None:
    with OUT_LOCK:
        sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
        sys.stdout.flush()


def _tools_list() -> list[dict]:
    out = []
    for t in worker.TOOLS:
        f = t["function"]
        eff = gate.TOOL_EFFECT.get(f["name"])
        out.append({"name": f["name"], "description": f["description"], "inputSchema": f["parameters"],
                    "annotations": {"readOnlyHint": eff == "read", "destructiveHint": eff == "delete",
                                    "openWorldHint": eff == "send"}})
    return out


TOOL_NAMES = {t["function"]["name"] for t in worker.TOOLS}


def _handle_call(mid, params: dict) -> None:
    name, args = params.get("name", ""), params.get("arguments") or {}
    try:
        if name not in TOOL_NAMES:
            result, is_err = {"error": f"unknown tool {name}"}, True
        else:
            result, is_err = call_tool(name, args if isinstance(args, dict) else {"_raw": args})
    except Exception as e:      # 서버 안 오류도 닫힌 쪽으로 — 실행하지 않았다고 알린다
        result, is_err = {"error": f"gate proxy error ({type(e).__name__}: {e}). The action was NOT executed."}, True
    _send({"jsonrpc": "2.0", "id": mid,
           "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}], "isError": is_err}})


def serve() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            m = json.loads(line)
        except json.JSONDecodeError:
            continue
        mid, method, params = m.get("id"), m.get("method"), m.get("params") or {}
        if method == "initialize":
            _send({"jsonrpc": "2.0", "id": mid, "result": {
                "protocolVersion": params.get("protocolVersion", "2025-06-18"),
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "moonjigi", "version": SERVER_VERSION},
                "instructions": "Mail, file and calendar tools. Every call is checked by the Moonjigi gate (Zoro-1) right before it runs; "
                                "a refused call returns an error and is not executed."}})
        elif method == "tools/list":
            _send({"jsonrpc": "2.0", "id": mid, "result": {"tools": _tools_list()}})
        elif method == "tools/call":
            threading.Thread(target=_handle_call, args=(mid, params), daemon=True).start()   # 추론 판정 중에도 ping에 답한다
        elif method == "ping":
            _send({"jsonrpc": "2.0", "id": mid, "result": {}})
        elif mid is not None and method:
            _send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {method}"}})
        # id 없는 알림(notifications/initialized 등)은 답하지 않는다


def main() -> int:
    signal.signal(signal.SIGTERM, lambda *_: (LOG.end("mcp session ended (SIGTERM)"), os._exit(0)))
    try:
        serve()
    finally:
        with STATE_LOCK:          # 돌고 있는 호출이 끝난 뒤에 닫는다
            LOG.end("mcp session ended")
    return 0


if __name__ == "__main__":
    sys.exit(main())
