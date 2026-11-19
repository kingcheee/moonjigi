#!/usr/bin/env python3
"""플레이그라운드 「강한 공격 던지기」 목록(web/redteam.json)을 밤새 공격 측정 기록에서 뽑는다(11-20 · HANDOFF-서사-배포-10 「계획」 2).

고르는 기준 — 「예전 판은 뚫렸는데 지금 판은 막는다」를 보여 주는 공격만:
  ① 공격(kind == "attack")
  ② v3b가 3회 중 한 번이라도 통과(variants_from_v2.derive(r)["v3b"][0] in PASS·MISSING)
  ③ v14가 3회 모두 멈춤(variants_v14.decide_v14(r, s)[0] not in PASS·MISSING)
  ④ 도구가 플레이그라운드 10개 중 하나 · user_request 500자 이하(server.py MAX_TASK)
입력: runs/attack-*-v2-r3/results.jsonl + attack-*-scenarios.json(같은 묶음 이름). 판정 서버를 부르지 않는다(기록 위 계산).

  python3 tools/build_redteam_json.py            # → web/redteam.json
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import variants_from_v2 as vv  # noqa: E402
import variants_v14 as v14  # noqa: E402

TOOLS = {"list_mail", "read_mail", "send_email", "search_files", "read_doc", "move_file", "delete_file", "share_link",
         "list_events", "create_event"}
STOP = lambda d: d not in ("PASS", "MISSING")  # noqa: E731


def main() -> int:
    out, seen = [], set()
    for run in sorted((ROOT / "runs").glob("attack-*-v2-r3")):
        bundle = run.name[len("attack-"):-len("-v2-r3")]
        sf = ROOT / f"attack-{bundle}-scenarios.json"
        res = run / "results.jsonl"
        if not sf.exists() or not res.exists():
            continue
        sc = {s["id"]: s for s in json.loads(sf.read_text(encoding="utf-8"))}
        reps = defaultdict(list)
        for line in res.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if r.get("kind") == "attack" and r["id"] in sc:
                reps[r["id"]].append(r)
        for sid, rs in reps.items():
            s = sc[sid]
            tc = s.get("tool_call") or {}
            if tc.get("name") not in TOOLS or len(s.get("user_request") or "") > 500:
                continue
            try:
                v3b = [vv.derive(r)["v3b"][0] for r in rs]
            except AssertionError:
                continue
            d14 = [v14.decide_v14(r, s)[0] for r in rs]
            if not any(not STOP(d) for d in v3b) or not all(STOP(d) for d in d14):
                continue
            key = (s["user_request"], json.dumps(tc, sort_keys=True, ensure_ascii=False))
            if key in seen:
                continue
            seen.add(key)
            out.append({"id": f"{bundle}/{sid}", "origin": s.get("origin") or "ours", "license": s.get("license"),
                        "origin_url": s.get("origin_url"), "technique": s.get("technique"),
                        "user_request": s["user_request"], "actions_so_far": s.get("actions_so_far") or [],
                        "source_text": (s.get("source_text") or "")[:4000], "tool_call": tc,
                        "measured": {"reps": len(rs), "v3b": v3b, "v14": d14}})
    dst = ROOT / "web" / "redteam.json"
    dst.write_text(json.dumps({"note": "밤새 공격 측정(v2 기록 3회)에서 예전 판 v3b가 한 번 이상 통과시켰고 v14가 3회 모두 멈춘 공격. "
                                       "실시간 판정은 기록과 다를 수 있다.", "v14": v14.V14_VERSION, "n": len(out), "items": out},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    by = defaultdict(int)
    for x in out:
        by[x["origin"]] += 1
    print(f"{len(out)}건 → {dst.relative_to(ROOT)}", dict(by))
    return 0


if __name__ == "__main__":
    sys.exit(main())
