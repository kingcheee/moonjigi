#!/usr/bin/env python3
"""묶음 하나의 뚫린 것·멈춘 정상을 건별로 — 보고서 「읽는 법」 쓰기용(11-20 hackathon-fd).

  python3 tools/attack_detail.py <이름>        (runs/attack-<이름>-v2-r3 · 시나리오 attack-<이름>-scenarios.json)

공격·애매: v3b·v10·v11·v12 중 하나라도 통과(PASS/MISSING)한 건 — 첫 반복 직답 match·injected·grade, 판별 결정(반복마다), v11 규칙.
정상: v3b·v10·v11·v12 중 하나라도 멈춘 건 — 판별 결정과 v10·v11 규칙.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import variants_from_v2 as vv  # noqa: E402
import variants_v7 as v7  # noqa: E402
import variants_v10 as v10  # noqa: E402
import variants_v11 as v11  # noqa: E402
import variants_v12 as v12  # noqa: E402
import variants_v13 as v13  # noqa: E402

name = sys.argv[1]
path = ROOT / "runs" / f"attack-{name}-v2-r3"
sc = v7.scenarios_for(path)
recs = [json.loads(x) for x in (path / "results.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
by = defaultdict(list)
for r in recs:
    by[r["id"]].append(r)

S = {"PASS": "P", "CONFIRM": "C", "BLOCK": "B", "MISSING": "M"}


def row(i: str) -> tuple[dict, str]:
    rs = sorted(by[i], key=lambda r: r["rep"])
    s = sc[i]
    d = {"v3b": [vv.derive(r)["v3b"][0] for r in rs],
         "v10": [v10.decide_v10(r, s)[0] for r in rs],
         "v11": [v11.decide_v11(r, s)[0] for r in rs],
         "v12": [v12.decide_v12(r, s)[0] for r in rs],
         "v13": [v13.decide_v13(r, s)[0] for r in rs]}
    rules = {"v12": v12.decide_v12(rs[0], s)[1], "v13": v13.decide_v13(rs[0], s)[1]}
    dr = rs[0]["verdict"].get("direct") or {}
    txt = (f"{i} {rs[0]['verdict']['tool']} · match {dr.get('match')} · inj {dr.get('injected')} · {dr.get('grade')} · "
           + " · ".join(f"{p} {''.join(S.get(x, '?') for x in d[p])}" for p in d)
           + f" · v12 규칙 「{rules['v12'][:90]}」 · v13 규칙 「{rules['v13'][:90]}」")
    return d, txt


for kind in ("attack", "ambiguous"):
    print(f"## {kind} — 통과가 하나라도 있는 건")
    for i in sorted(i for i in by if by[i][0]["kind"] == kind):
        d, txt = row(i)
        if any({"PASS", "MISSING"} & set(v) for v in d.values()):
            print("-", txt, "|", sc[i].get("technique", ""), "|", json.dumps(sc[i]["tool_call"]["args"], ensure_ascii=False)[:160])
print("## normal — 멈춘 것이 하나라도 있는 건")
for i in sorted(i for i in by if by[i][0]["kind"] == "normal"):
    d, txt = row(i)
    if any(x != "PASS" for v in d.values() for x in v):
        print("-", txt, "|", sc[i]["user_request"][:60])
