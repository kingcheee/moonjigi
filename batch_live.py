#!/usr/bin/env python3
"""라이브 장면을 여러 번 돌려 분포만 잰다 — 정책·일꾼은 고치지 않는다(측정 전용). 표준 라이브러리만.

  python3 batch_live.py --plan refund-reply:10:deny vendor-reply:10:approve file-move:3 meeting:3 inbox-summary:3 \
      --out runs/m4-batch-1519

판마다: 결정 순서 · 직답 ms · 추론 s · 사람 확인 수 · 끝난 이유 · 벽시계 · 보낸 메일. 판은 순서대로(동시 실행은 지연을 흐린다).
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.request
from pathlib import Path


def req(base, path, body=None):
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    r = urllib.request.Request(base.rstrip("/") + path, data=data, headers={"content-type": "application/json"})
    with urllib.request.urlopen(r, timeout=60) as f:
        return json.load(f)


def one(base, scene, confirm):
    rid = req(base, "/worker/run", {"scene": scene})["run_id"]
    seen, evs, answered = 0, [], set()
    while True:
        d = req(base, f"/worker/events?run={rid}&since={seen}")
        for ev in d["events"]:
            seen += 1
            evs.append(ev)
            if ev["type"] == "confirm_wait" and ev["call_id"] not in answered:
                answered.add(ev["call_id"])
                req(base, "/worker/confirm", {"run": rid, "approve": confirm == "approve"})
        if d["done"] and not d["events"]:
            break
        time.sleep(0.2)
    finals = [e for e in evs if e["type"] == "verdict" and e.get("final")]
    end = next((e for e in evs if e["type"] == "run_end"), {})
    calls = {e["call_id"]: e["name"] for e in evs if e["type"] == "tool_call"}
    return {
        "run_id": rid, "scene": scene,
        "decisions": [f"{calls.get(e['call_id'])}:{e['verdict']['decision']}" for e in finals],
        "direct_ms": [e["verdict"]["ms"].get("direct") for e in finals],
        "reason_s": [round(e["verdict"]["ms"]["reasoned"] / 1000, 1) for e in finals if "reasoned" in e["verdict"]["ms"]],
        "cut": [e["verdict"].get("cut") for e in finals if "reasoned" in e["verdict"]["ms"]],
        "confirms": sum(e["type"] == "confirm_wait" for e in evs),
        "end": end.get("reason"), "wall_s": end.get("wall_s"), "steps": end.get("steps"),
        "outbox": end.get("outbox"),
        "first_risky": next((f"{calls.get(e['call_id'])}:{e['verdict']['decision']}" for e in finals
                             if calls.get(e["call_id"]) in ("send_email", "share_link", "delete_file", "delete_mail")), None),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8899")
    ap.add_argument("--plan", nargs="+", required=True, help="scene:N[:deny|approve]")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    health = req(a.base, "/health")
    rows = []
    with open(out / "runs.jsonl", "a", encoding="utf-8") as f:
        for item in a.plan:
            parts = item.split(":")
            scene, n, confirm = parts[0], int(parts[1]), (parts[2] if len(parts) > 2 else "deny")
            for i in range(n):
                r = one(a.base, scene, confirm)
                r["confirm_policy"] = confirm
                rows.append(r)
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
                f.flush()
                print(f"{scene} {i + 1}/{n} {r['end']} wall={r['wall_s']}s risky={r['first_risky']} reason_s={r['reason_s']}", flush=True)
    L = [f"# 라이브 일꾼 반복 측정 — {out.name}", "",
         f"- 게이트 정책 {health.get('policy')} `{health.get('policy_version')}` · {time.strftime('%F %T')} · 측정 전용(정책·일꾼 수정 없음)", "",
         "| 장면 | 판 | 끝난 이유(횟수) | 위험 호출 최종 결정(횟수) | 추론 s p50 / 최대 | 벽시계 s p50 / 최대 |", "|---|---|---|---|---|---|"]
    for scene in dict.fromkeys(r["scene"] for r in rows):
        rs = [r for r in rows if r["scene"] == scene]
        ends, risky = {}, {}
        for r in rs:
            ends[r["end"]] = ends.get(r["end"], 0) + 1
            risky[str(r["first_risky"])] = risky.get(str(r["first_risky"]), 0) + 1
        rsn = [s for r in rs for s in r["reason_s"]]
        walls = [r["wall_s"] for r in rs if r["wall_s"] is not None]
        L.append(f"| {scene} | {len(rs)} | {' · '.join(f'{k} {v}' for k, v in ends.items())} | "
                 f"{' · '.join(f'{k} {v}' for k, v in risky.items())} | "
                 + (f"{statistics.median(rsn):.1f} / {max(rsn):.1f}" if rsn else "—") + " | "
                 + (f"{statistics.median(walls):.1f} / {max(walls):.1f}" if walls else "—") + " |")
    (out / "summary.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
