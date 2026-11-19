#!/usr/bin/env python3
"""문지기 일꾼 원격 조종 — 게이트 서버(server.py)의 /worker/*를 불러 한 판을 돌리고 이벤트를 찍는다. 표준 라이브러리만.

  python3 drive.py --scene refund-reply --confirm deny          # 사람 확인이 뜨면 거절
  python3 drive.py --scene vendor-reply --confirm approve
  python3 drive.py --replay <run_id>                            # 저장된 판 다시 보기
  python3 drive.py --runs                                       # 저장된 판 목록
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request


def req(base, path, body=None):
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    r = urllib.request.Request(base.rstrip("/") + path, data=data, headers={"content-type": "application/json"})
    with urllib.request.urlopen(r, timeout=60) as f:
        return json.load(f)


def line(ev):
    v = ev.get("verdict") or {}
    if v:
        p = v.get("reasoned") or v.get("direct") or {}
        ms = v.get("ms") or {}
        return (f"{ev['type']:13} {v.get('decision'):7} {'(final)' if ev.get('final') else '       '} stage={v.get('stage'):8} "
                f"match={p.get('match', 0):.2f} inj={p.get('injected', 0):.2f}{'' if p.get('injected_asked') else '*'} "
                f"undo={p.get('undo', 0):.2f} grade={p.get('grade')} · {v.get('rule')} · direct {ms.get('direct')}ms"
                + (f" + reason {ms['reasoned'] / 1000:.1f}s" if 'reasoned' in ms else ""))
    d = {k: ev[k] for k in ("name", "args", "content", "result", "reason", "approve", "by", "executed", "task", "outbox") if k in ev}
    return f"{ev['type']:13} {json.dumps(d, ensure_ascii=False)[:230]}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8899")
    ap.add_argument("--scene")
    ap.add_argument("--worker-prompt", default="plain", choices=["plain", "compliant"])
    ap.add_argument("--confirm", default="deny", choices=["deny", "approve", "ask"])
    ap.add_argument("--replay")
    ap.add_argument("--policy", default=None, help="v1·v2·v3·v3b·v3c — 없으면 게이트 서버 기본값")
    ap.add_argument("--rules", nargs="*", default=None, help="회사 규칙 스위치(예: --rules pii)")
    ap.add_argument("--runs", action="store_true")
    a = ap.parse_args()
    if a.runs:
        for r in req(a.base, "/worker/runs"):
            print(f"{r['run_id']:32} {str(r['scene']):14} {r['worker_prompt'] or '':9} {str(r['end']):40} {r['decisions']}")
        return 0
    body = {"scene": a.scene, "worker_prompt": a.worker_prompt}
    if a.policy:
        body["policy"] = a.policy
    if a.rules:
        body["rules"] = a.rules
    rid = a.replay or req(a.base, "/worker/run", body)["run_id"]
    print("run", rid)
    seen, answered = 0, set()
    while True:
        d = req(a.base, f"/worker/events?run={rid}&since={seen}")
        for ev in d["events"]:
            seen += 1
            print(f"{ev['seq']:3} {line(ev)}", flush=True)
            if ev["type"] == "confirm_wait" and d.get("live") and ev["call_id"] not in answered:
                answered.add(ev["call_id"])
                approve = a.confirm == "approve" or (a.confirm == "ask" and input("  허락? [y/N] ").strip().lower() == "y")
                print("  →", req(a.base, "/worker/confirm", {"run": rid, "approve": approve}))
        if d["done"] and not d["events"]:
            break
        time.sleep(0.2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
