#!/usr/bin/env python3
"""공격 측정 원장 — 해커톤 동안 네이버 서버에서 잰 공격 묶음을 한 표로 모은다(다시 돌리면 갱신).

  python3 tools/attack_ledger.py > runs/attack-ledger.md

묶음마다: 측정 시작(runs/attack-<이름>.meta) · 성격(시나리오 origin·set_note) · 건수 · 대표 v3b와 비교군(보고서 요약 표) ·
v6～v12 후보(variants_v11.count · variants_v12.count — v2 기록에서 계산). 보고서(runs/attack-<이름>-report.md)가 없는 묶음(측정 중)은 뺀다.
숫자는 3회 반복 불리하게 셈(공격은 한 번이라도 통과면 통과 · 정상은 한 번이라도 멈추면 멈춤) · 비교군은 1회.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import variants_v11 as v11  # noqa: E402
import variants_v12 as v12  # noqa: E402
import variants_v13 as v13  # noqa: E402

FIX = {"v6": "45fc5cc 01:04", "v7": "91df552 02:00", "v8": "bc7ccc8 03:20", "v9": "2365d48 03:46", "v10": "8e4593b 05:11", "v11": "a79d3a6 05:37", "v12": "14c3b2c 06:03", "v13": "86d6923 06:22"}


def kind_of(sc: list[dict]) -> str:
    o = {x.get("origin") for x in sc}
    note = " ".join({x.get("set_note", "") for x in sc})
    if o == {"ours"}:
        if "짝 대조" in note:
            return "우리 짝 대조(어려운 정상)"
        if "적응형 묶음 3" in note:
            return "우리 적응형 3(v11 피하기)"
        if "적응형 묶음 2" in note:
            return "우리 적응형 2(v10 출처 피하기)"
        if "적응형" in note:
            return "우리 적응형(v9 낱말 피하기)"
        if "적대적" in note:
            return "우리 적대적"
        return "우리 일반"
    return "공개 · " + ", ".join(sorted(x for x in o if x))


def summary(report: Path) -> dict:
    out = {}
    for L in report.read_text(encoding="utf-8").splitlines():
        c = [x.strip() for x in L.strip().strip("|").split("|")]
        if len(c) > 7 and (c[0].startswith("**v3b") or c[0] == "비교군"):
            out["v3b" if c[0].startswith("**v3b") else "gen"] = (c[3], c[6])
    return out


rows = []
for meta in sorted((HERE / "runs").glob("attack-*.meta")):
    name = meta.stem
    if name.endswith("-genonly") or "calib" in name:
        continue
    rep = HERE / "runs" / f"{name}-report.md"
    run = HERE / "runs" / f"{name}-v2-r3"
    scp = HERE / f"{name}-scenarios.json"
    if not (rep.exists() and run.exists() and scp.exists()):
        continue
    start = re.search(r"start=(\S+ \S+)", meta.read_text(encoding="utf-8")).group(1)
    sc = json.loads(scp.read_text(encoding="utf-8"))
    n = {k: sum(1 for x in sc if x["kind"] == k) for k in ("attack", "normal", "ambiguous")}
    s = summary(rep)
    c = v11.count(run)
    c13 = v13.count(run)
    c["v12"], c["v13"] = c13["v12"], c13["v13"]
    vs = {p: (len(c[p]["attack_passed"]), len(c[p]["normal_stopped"]) if n["normal"] else None) for p in ("v6", "v7", "v8", "v9", "v10", "v11", "v12", "v13")}
    rows.append((start, name.removeprefix("attack-"), kind_of(sc), n, s, vs))

rows.sort()
print("# 공격 측정 원장 — 트릴리온 해커톤 본선(네이버 L40S · 판정 서버 127.0.0.1:30001 직접)\n")
print("`python3 tools/attack_ledger.py`로 만든다. 숫자 = 3회 반복 불리하게 셈(비교군 1회). 칸은 「공격 통과 / 정상 멈춤」, 정상 대조가 없으면 공격만.")
print("v3b = 대표 판(측정 전에 정해 둔 대표 행 · 해시 060839ee0c12) · 비교군 = 같은 Zoro-1에게 글로 판정(thinking off) · v6～v13 = v2 측정 기록에서 계산한 후보 판(서버에 올리지 않음).")
print("후보 판 고정 시각: " + " · ".join(f"{k} {v}" for k, v in FIX.items()) + " — 고정 뒤에 결과를 연 묶음이 그 판의 「안 본 자료」다(보고서 「비교」 절에 묶음마다 적음).\n")
print("| 측정 시작 | 묶음 | 성격 | 공격·정상·애매 | v3b | 비교군 | v6 | v7 | v8 | v9 | v10 | v11 | v12 | v13 |")
print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
tot = {"att": 0, "nor": 0, "scen": 0}
for start, name, kind, n, s, vs in rows:
    has_n = n["normal"] > 0
    has_a = n["attack"] > 0
    f = (lambda a, b: (f"{a}/{n['attack']}" if has_a else "") + (" · " if has_a and has_n else "") + (f"{b}/{n['normal']}" if has_n else ""))
    v3b = s.get("v3b", ("?", "?"))
    gen = s.get("gen", ("?", "?"))
    cell = lambda t: " · ".join(x for x, ok in ((t[0], has_a), (t[1], has_n)) if ok)  # noqa: E731
    print(f"| {start[5:16]} | {name} | {kind} | {n['attack']}·{n['normal']}·{n['ambiguous']} | {cell(v3b)} | {cell(gen)} | "
          + " | ".join(f(*vs[p]) for p in ("v6", "v7", "v8", "v9", "v10", "v11", "v12", "v13")) + " |")
    tot["att"] += n["attack"]; tot["nor"] += n["normal"]; tot["scen"] += sum(n.values())
print(f"\n묶음 {len(rows)}개 · 시나리오 {tot['scen']}건(공격 {tot['att']} · 정상 {tot['nor']}) · 각 3회 반복 + 회사 규칙 판 1회 + 비교군 1회.")
