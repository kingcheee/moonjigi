#!/usr/bin/env python3
"""문지기 HTTP 서버 — gate.py를 감싸 화면·일꾼이 부르게 한다. 표준 라이브러리만.

판정 서버(Zoro-1 `serve.py --mode decide`)와 같은 기계에서 띄운다 — 직답 0.1초가 터널 왕복에 먹히지 않게.

  POST /gate/direct   {call}                 → 직답 verdict를 바로 돌려준다. needs_reason이면 reason_id가 붙는다
  POST /gate/reason   {"reason_id": "..."}   → 추론 후 재판정 verdict (1~수십 초)
  POST /gate          {call}                 → 사다리 전체(블로킹)
  GET  /health                               → policy_version · 판정 서버 상태
  GET  /log?n=50                             → 최근 검문 기록(JSONL 꼬리)
  M4 일꾼(worker.py):
  GET  /worker/scenes                        → 장면 목록 {id: {title, kind, task}}
  POST /worker/run {"scene", "worker_prompt"?: plain|compliant, "think"?, "task"?} → {"run_id"} (서버 안에서 돈다)
  GET  /worker/events?run=ID&since=N         → {"events": [...], "done", "waiting", "live"} — 저장된 판도 같은 모양(재생)
  POST /worker/confirm {"run", "approve"}    → 사람 확인 대기 중인 호출을 허락/거절
  GET  /worker/runs                          → 저장된 판 목록(재생용)
  GET  /…                                    → web/ 정적 파일(데모 화면)

  python3 server.py --upstream http://127.0.0.1:30001 --port 8899
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import sys
import threading
import time
import traceback
import urllib.parse
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gate  # noqa: E402
import worker  # noqa: E402

HERE = Path(__file__).resolve().parent
RUNS: dict[str, "worker.Run"] = {}
PENDING: dict[str, tuple[float, dict, dict]] = {}   # reason_id → (만든 시각, call, direct verdict)
PENDING_TTL = 600
LOCK = threading.Lock()
CFG = {"upstream": "http://127.0.0.1:30001", "log": HERE / "logs" / "gate.jsonl", "web": HERE / "web"}
# 공개 서버 보호(11-19 서사·배포 쪽 부탁) — 판정 결과·정책 해시와 무관한 입구 검사뿐이다
MAX_BODY = 64 * 1024          # 요청 본문 상한 → 413
MAX_LIVE_RUNS = 2             # 동시에 도는 라이브 일꾼 판 → 429
MAX_TASK = 500                # task·user_request 글자 상한 → 400
MAX_SOURCE = 20_000           # source_text 글자 상한 → 400 (판정 state에는 어차피 앞 4,000자만 들어간다)


def _log(kind: str, call: dict, verdict: dict) -> None:
    CFG["log"].parent.mkdir(parents=True, exist_ok=True)
    with LOCK, open(CFG["log"], "a", encoding="utf-8") as f:
        f.write(json.dumps({"t": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "kind": kind, "call": call, "verdict": verdict},
                           ensure_ascii=False) + "\n")


def _gc() -> None:
    now = time.time()
    with LOCK:
        for k in [k for k, (t, _, _) in PENDING.items() if now - t > PENDING_TTL]:
            PENDING.pop(k, None)


def _rules(body: dict) -> list | None:
    """요청의 "rules": ["pii"] — 모르는 규칙 이름은 버린다. 없으면 None(지금과 동일)."""
    r = body.get("rules")
    if not isinstance(r, list):
        return None
    r = [x for x in r if isinstance(x, str) and x in gate.RULES]
    return r or None


def _validate(call: dict) -> str | None:
    if not isinstance(call, dict):
        return "call must be an object"
    if not call.get("user_request"):
        return "user_request is required"
    if not isinstance(call["user_request"], str) or len(call["user_request"]) > MAX_TASK:
        return f"user_request must be a string of at most {MAX_TASK} chars"
    src = call.get("source_text")
    if src is not None and (not isinstance(src, str) or len(src) > MAX_SOURCE):
        return f"source_text must be a string of at most {MAX_SOURCE} chars"
    tc = call.get("tool_call")
    if not isinstance(tc, dict) or not tc.get("name"):
        return "tool_call.name is required"
    return None


class H(BaseHTTPRequestHandler):
    server_version = "moonjigi/1"

    def log_message(self, fmt, *args):  # 조용히 — 검문 기록은 JSONL로 남는다
        pass

    def _send(self, code: int, obj=None, body: bytes | None = None, ctype="application/json; charset=utf-8"):
        if body is None:
            body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("content-type", ctype)
        self.send_header("content-length", str(len(body)))
        self.send_header("access-control-allow-origin", "*")
        self.send_header("access-control-allow-headers", "content-type")
        self.send_header("access-control-allow-methods", "GET, POST, OPTIONS")
        self.send_header("cache-control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send(204, body=b"")

    def _body(self) -> dict:
        n = int(self.headers.get("content-length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_POST(self):
        path = self.path.split("?")[0].rstrip("/")
        try:
            n = int(self.headers.get("content-length") or 0)
        except ValueError:
            return self._send(400, {"error": "bad content-length"})
        if n > MAX_BODY:
            self.close_connection = True
            return self._send(413, {"error": f"request body over {MAX_BODY} bytes"})
        try:
            body = self._body()
        except Exception as e:
            return self._send(400, {"error": f"bad json: {e}"})
        try:
            if path == "/gate/direct":
                call = body.get("call", body)
                if err := _validate(call):
                    return self._send(400, {"error": err})
                v = gate.check_direct(CFG["upstream"], call, body.get("policy") or None, _rules(body))
                v["ms"]["total"] = v["ms"]["direct"]
                if v["needs_reason"]:
                    _gc()
                    rid = uuid.uuid4().hex[:12]
                    with LOCK:
                        PENDING[rid] = (time.time(), call, v)
                    v["reason_id"] = rid
                _log("direct", call, v)
                return self._send(200, v)
            if path == "/gate/reason":
                rid = body.get("reason_id", "")
                with LOCK:
                    item = PENDING.pop(rid, None)
                if not item:
                    return self._send(404, {"error": "unknown or expired reason_id"})
                _, call, v0 = item
                v = gate.check_reason(CFG["upstream"], call, v0)
                v["reason_id"] = rid
                _log("reason", call, v)
                return self._send(200, v)
            if path == "/gate":
                call = body.get("call", body)
                if err := _validate(call):
                    return self._send(400, {"error": err})
                v = gate.check(CFG["upstream"], call, escalate=not body.get("direct_only"), pv=body.get("policy") or None,
                               rules=_rules(body))
                _log("ladder", call, v)
                return self._send(200, v)
            if path == "/worker/run":
                scene = body.get("scene", "")
                scenes = json.loads(worker.SCENES.read_text(encoding="utf-8"))
                if scene not in scenes:
                    return self._send(400, {"error": f"unknown scene: {scene}", "scenes": list(scenes)})
                task = body.get("task")
                if task is not None and (not isinstance(task, str) or len(task) > MAX_TASK):
                    return self._send(400, {"error": f"task must be a string of at most {MAX_TASK} chars"})
                with LOCK:
                    live = sum(1 for x in RUNS.values() if not x.done)
                if live >= MAX_LIVE_RUNS:
                    return self._send(429, {"error": f"{live} live runs already running (max {MAX_LIVE_RUNS}) — try again shortly"})
                r = worker.Run(scene, CFG["upstream"], body.get("worker_prompt", "plain"), bool(body.get("think")),
                               body.get("task") or None, rules=_rules(body), policy=body.get("policy") or None)
                with LOCK:
                    RUNS[r.id] = r
                threading.Thread(target=r.run, daemon=True).start()
                return self._send(200, {"run_id": r.id, "scene": scene, "task": r.task})
            if path == "/worker/confirm":
                r = RUNS.get(body.get("run", ""))
                if not r:
                    return self._send(404, {"error": "no live run with that id"})
                ok = r.confirm(bool(body.get("approve")))
                return self._send(200 if ok else 409, {"ok": ok, "waiting": r.waiting_call})
            return self._send(404, {"error": "no such endpoint"})
        except urllib.error.URLError as e:
            return self._send(502, {"error": f"judge server unreachable: {e}"})
        except Exception as e:
            traceback.print_exc()
            return self._send(500, {"error": f"{type(e).__name__}: {e}"})

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/health":
            try:
                with urllib.request.urlopen(CFG["upstream"].rstrip("/") + "/v1/models", timeout=3) as r:
                    up = json.load(r)
                ok = True
            except Exception as e:
                up, ok = str(e), False
            return self._send(200, {"ok": ok, "policy": gate.ACTIVE, "policy_version": gate.active_version(), "policy_versions": gate.POLICY_VERSIONS,
                                    "rules": {k: {"text": r["text"], "threshold": r["threshold"], "effect": r["effect"]} for k, r in gate.RULES.items()},
                                    "rules_version": gate.RULES_VERSION, "upstream": CFG["upstream"],
                                    "models": up, "pending": len(PENDING)})
        if path == "/log":
            n = 50
            if "n=" in self.path:
                try:
                    n = int(self.path.split("n=")[1].split("&")[0])
                except ValueError:
                    pass
            lines = CFG["log"].read_text(encoding="utf-8").splitlines()[-n:] if CFG["log"].exists() else []
            return self._send(200, [json.loads(x) for x in lines])
        if path == "/worker/scenes":
            scenes = json.loads(worker.SCENES.read_text(encoding="utf-8"))
            return self._send(200, {k: {f: v.get(f) for f in ("title", "kind", "task")} for k, v in scenes.items()})
        if path == "/worker/events":
            q = dict(x.split("=", 1) for x in self.path.split("?", 1)[1].split("&") if "=" in x) if "?" in self.path else {}
            rid, since = urllib.parse.unquote(q.get("run", "")), int(q.get("since", "0") or 0)
            r = RUNS.get(rid)
            if r:
                return self._send(200, {"run_id": rid, "events": r.since(since), "done": r.done,
                                        "waiting": r.waiting_call, "live": True})
            evs = worker.load_saved(rid)
            if evs is None:
                return self._send(404, {"error": "unknown run"})
            return self._send(200, {"run_id": rid, "events": evs[since:], "done": True, "waiting": None, "live": False})
        if path == "/worker/runs":
            out = []
            for p in sorted(worker.RUNS_DIR.glob("*.jsonl"), reverse=True)[:100]:
                lines = p.read_text(encoding="utf-8").splitlines()
                first = json.loads(lines[0]) if lines else {}
                last = json.loads(lines[-1]) if lines else {}
                finals = [json.loads(x).get("verdict", {}).get("decision") for x in lines
                          if '"final": true' in x and '"type": "verdict"' in x]
                out.append({"run_id": p.stem, "scene": first.get("scene"), "task": first.get("task"),
                            "worker_prompt": first.get("worker_prompt"), "policy_version": first.get("policy_version"),
                            "done": last.get("type") == "run_end", "end": last.get("reason"), "decisions": finals})
            return self._send(200, out)
        # 정적 파일
        rel = path.lstrip("/") or "index.html"
        f = (CFG["web"] / rel).resolve()
        if not str(f).startswith(str(CFG["web"].resolve())) or not f.is_file():
            if rel == "index.html":
                return self._send(200, {"moonjigi": "gate server", "policy_version": gate.active_version(),
                                        "endpoints": ["POST /gate/direct", "POST /gate/reason", "POST /gate",
                                                      "GET /health", "GET /log"]})
            return self._send(404, {"error": "not found"})
        ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        return self._send(200, body=f.read_bytes(), ctype=ctype)


def main() -> int:
    ap = argparse.ArgumentParser(description="문지기 HTTP 서버")
    ap.add_argument("--upstream", default=CFG["upstream"], help="Zoro-1 판정 서버")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8899)
    ap.add_argument("--log", default=str(CFG["log"]))
    ap.add_argument("--web", default=str(CFG["web"]))
    ap.add_argument("--policy", default="v2", choices=list(gate.POLICY_FUNCS))
    a = ap.parse_args()
    CFG.update(upstream=a.upstream, log=Path(a.log), web=Path(a.web))
    gate.ACTIVE = a.policy
    srv = ThreadingHTTPServer((a.host, a.port), H)
    print(f"moonjigi gate on http://{a.host}:{a.port} → judge {a.upstream} · policy {gate.ACTIVE} {gate.active_version()}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
