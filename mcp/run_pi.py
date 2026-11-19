#!/usr/bin/env python3
"""pi 에이전트로 한 판 돌리기 — 일꾼은 pi(아무 모델), 도구는 문지기 MCP 서버(moonjigi_mcp.py)를 통해서만.

전역 pi 설정(~/.pi/agent)은 건드리지 않는다. 이 폴더의 `.pi-agent/`(git 제외)를 pi 설정 폴더로 쓰고,
거기에 인증 파일 링크와 MCP 등록(mcp.json) 한 건만 둔다 — 전역 AGENTS.md·확장·다른 MCP 서버는 실리지 않는다.

  python3 mcp/run_pi.py --scene refund-reply
  python3 mcp/run_pi.py --scene doc-wipe --runs 3
  python3 mcp/run_pi.py --scene refund-reply --gate http://127.0.0.1:9 --tag gate-down     # 문지기를 끊은 판
  python3 mcp/run_pi.py --scene refund-reply --rules pii                                   # 회사 규칙 한 줄 켜기(서버가 지원할 때)

남는 것: runs-live/<run_id>.jsonl (worker.py와 같은 이벤트 모양 — viewer.html 재생) · mcp/logs/<run_id>.pi.jsonl (pi --mode json 원본)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import worker  # noqa: E402

AGENT_DIR = HERE / ".pi-agent"
LOGS = HERE / "logs"
DEFAULT_MODEL = "openrouter/nvidia/nemotron-3-ultra-550b-a55b:free"


def setup_agent_dir(pi_home: Path, env: dict) -> None:
    AGENT_DIR.mkdir(exist_ok=True)
    for name in ("auth.json", "models-store.json"):      # 키는 복사하지 않고 링크만 건다
        src, dst = pi_home / name, AGENT_DIR / name
        if src.exists() and not dst.exists():
            dst.symlink_to(src)
    cfg = {"mcpServers": {"moonjigi": {
        "command": sys.executable or "python3", "args": [str(HERE / "moonjigi_mcp.py")], "env": env,
        "exposure": "direct", "timeout": 300,
        "description": "Mail, file and calendar tools, each call checked by the Moonjigi gate before it runs"}}}
    (AGENT_DIR / "mcp.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")


def assistant_events(pi_log: Path) -> tuple[list[dict], list[str]]:
    """pi 원본 로그에서 일꾼이 한 말(도구 없이 한 말·마지막 답)과 오류를 뽑는다."""
    evs, errors = [], []
    if not pi_log.is_file():
        return evs, ["no pi log"]
    for line in pi_log.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        m = e.get("message") or {}
        if e.get("type") == "message_end" and m.get("role") == "assistant":
            parts = m.get("content") or []
            text = "".join(p.get("text", "") for p in parts if isinstance(p, dict) and p.get("type") == "text").strip()
            has_call = any(isinstance(p, dict) and p.get("type") == "toolCall" for p in parts)
            if m.get("stopReason") in ("error", "aborted") or m.get("errorMessage"):
                errors.append(str(m.get("errorMessage") or m.get("stopReason"))[:300])
            if text:
                evs.append({"t": round((m.get("timestamp") or 0) / 1000, 3), "type": "assistant", "content": text, "final": not has_call})
    return evs, errors


def merge(events_path: Path, pi_log: Path, meta: dict, pi_exit: int) -> list[dict]:
    evs = [json.loads(x) for x in events_path.read_text(encoding="utf-8").splitlines() if x.strip()] if events_path.is_file() else []
    says, errors = assistant_events(pi_log)
    if not evs:      # 도구를 한 번도 안 부른 판 — MCP 서버가 기록을 열지 않았다
        evs = [{"t": meta["t0"], "type": "run_start", **meta["start"]}]
    end = next((e for e in evs if e["type"] == "run_end"), None)
    body = sorted([e for e in evs if e["type"] != "run_end"] + says, key=lambda e: (e["type"] != "run_start", e["t"]))
    if end is None:
        end = {"t": round(time.time(), 3), "type": "run_end", "reason": "no tool calls" if len(evs) == 1 else "mcp server did not close cleanly",
               "steps": sum(1 for e in evs if e["type"] == "tool_call"), "wall_s": round(time.time() - meta["t0"], 1),
               "outbox": [], "trash": [], "shared": []}
    end.update(pi_exit=pi_exit, pi_errors=errors)
    out = body + [end]
    for i, e in enumerate(out):
        e["seq"] = i
    events_path.parent.mkdir(parents=True, exist_ok=True)
    events_path.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in out), encoding="utf-8")
    return out


def one_run(a, scene: dict, i: int) -> dict:
    task = a.task or scene["task"]
    tag = f"-{a.tag}" if a.tag else ""
    run_id = f"pi-{time.strftime('%H%M%S')}-{a.scene}{tag}-{uuid.uuid4().hex[:4]}"
    runs_dir = Path(a.runs_dir) if a.runs_dir else worker.RUNS_DIR
    events_path = runs_dir / f"{run_id}.jsonl"
    LOGS.mkdir(exist_ok=True)
    pi_log, pi_err = LOGS / f"{run_id}.pi.jsonl", LOGS / f"{run_id}.pi.err"
    worker_name = "pi/" + a.model
    env = {"MOONJIGI_GATE": a.gate, "MOONJIGI_SCENE": a.scene, "MOONJIGI_TASK": task, "MOONJIGI_WORKER": worker_name,
           "MOONJIGI_EVENTS": str(events_path), "MOONJIGI_RULES": a.rules or "", "MOONJIGI_POLICY": a.policy or ""}
    setup_agent_dir(Path(a.pi_home).expanduser(), env)
    system = time.strftime("Today is %Y-%m-%d (%A). ") + worker.WORKER_PROMPTS["plain"]     # Zoro-1 일꾼과 같은 시스템 프롬프트
    cmd = ["pi", "-p", "--mode", "json", "--no-session", "--no-approve", "-nbt", "-ns", "-nc", "-np", "--thinking", a.thinking,
           "--model", a.model, "--system-prompt", system, task]
    t0 = time.time()
    with open(pi_log, "w", encoding="utf-8") as out, open(pi_err, "w", encoding="utf-8") as err:
        try:
            rc = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=out, stderr=err, cwd=str(HERE), timeout=a.timeout,
                                env={**os.environ, "PI_CODING_AGENT_DIR": str(AGENT_DIR)}).returncode
        except subprocess.TimeoutExpired:
            rc = 124
    for _ in range(40):       # MCP 서버가 run_end를 쓸 때까지 잠깐 기다린다(pi가 stdin을 닫으면 쓴다)
        if events_path.is_file() and '"type": "run_end"' in events_path.read_text(encoding="utf-8"):
            break
        time.sleep(0.25)
    meta = {"t0": round(t0, 3), "start": dict(scene=a.scene, title=scene.get("title"), task=task, worker=worker_name, via="mcp",
                                               worker_prompt=f"{worker_name} · MCP", think=False, gate=a.gate, rules=[r for r in (a.rules or "").split(",") if r])}
    evs = merge(events_path, pi_log, meta, rc)
    calls = {e["call_id"]: {"name": e["name"], "args": e["args"]} for e in evs if e["type"] == "tool_call"}
    for e in evs:
        if e["type"] == "verdict" and e.get("final"):
            calls[e["call_id"]].update(decision=e["verdict"].get("decision"), rule=e["verdict"].get("rule"), stage=e["verdict"].get("stage"))
        if e["type"] == "tool_result":
            calls[e["call_id"]]["executed"] = e["executed"]
    end = evs[-1]
    print(f"\n[{i}] {run_id} · pi exit {rc} · {time.time() - t0:.1f}s · {end.get('reason')}")
    for c in calls.values():
        print(f"    {c['name']:13} {c.get('decision', '?'):8} {'실행' if c.get('executed') else '거부'}  {c.get('rule', '')}  {json.dumps(c['args'], ensure_ascii=False)[:150]}")
    final = next((e["content"] for e in reversed(evs) if e["type"] == "assistant" and e.get("final")), "")
    print(f"    마지막 답: {final[:300]!r}")
    if end.get("pi_errors"):
        print(f"    ⚠ pi 오류: {end['pi_errors']}")
    print(f"    outbox {len(end.get('outbox') or [])} · trash {len(end.get('trash') or [])} · shared {len(end.get('shared') or [])} · 기록 {events_path}")
    return {"run_id": run_id, "rc": rc, "calls": list(calls.values()), "end": end, "final": final}


def main() -> int:
    ap = argparse.ArgumentParser(description="pi + 문지기 MCP — 한 판 돌리기")
    ap.add_argument("--scene", required=True)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--gate", default=os.environ.get("MOONJIGI_GATE", "http://127.0.0.1:8899"))
    ap.add_argument("--rules", default="", help="켤 회사 규칙(쉼표 구분) — 예: pii")
    ap.add_argument("--policy", default="", help="정책 판(v1|v2|v3|v3b|v3c) — 없으면 문지기 서버 기본값")
    ap.add_argument("--task", help="장면의 task 대신 쓸 사용자 요청")
    ap.add_argument("--tag", default="", help="run_id에 붙일 꼬리표 (예: gate-down)")
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--thinking", default="off")
    ap.add_argument("--timeout", type=float, default=420)
    ap.add_argument("--runs-dir", help="기록 폴더(기본 ../runs-live)")
    ap.add_argument("--pi-home", default="~/.pi/agent", help="인증 파일을 링크해 올 pi 설정 폴더")
    a = ap.parse_args()
    scenes = json.loads(worker.SCENES.read_text(encoding="utf-8"))
    extra = HERE / "scenes_extra.json"
    if extra.is_file():
        scenes = {**json.loads(extra.read_text(encoding="utf-8")), **scenes}
    if a.scene not in scenes:
        print(f"unknown scene {a.scene!r} — have {sorted(scenes)}", file=sys.stderr)
        return 2
    for i in range(1, a.runs + 1):
        one_run(a, scenes[a.scene], i)
    return 0


if __name__ == "__main__":
    sys.exit(main())
