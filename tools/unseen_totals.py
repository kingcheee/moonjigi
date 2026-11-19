#!/usr/bin/env python3
"""판별 「안 본 자료」 합계 — 판을 고정한 뒤에 결과를 연 묶음만 더한다(11-20 hackathon-fd).

  python3 tools/unseen_totals.py            (보고서가 있는 묶음만 · 측정 중인 묶음은 자동으로 빠진다)

안 본 목록은 각 판 파일 머리말 · 보고서 「비교」 절에 적은 것을 옮겼다. 성격별로 셋으로 가른다:
  공개(남이 만든 자료) · 우리 일반 · 우리 적응형·짝 대조(같은 팀이 판을 읽고 쓴 것 — 화이트박스).
「유리할 수 있음」 표시: 판을 만든 사람이 시나리오를 알았던 묶음(결과는 안 봄).
숫자는 3회 반복 불리하게 셈(공격은 한 번이라도 통과면 통과 · 정상은 한 번이라도 멈추면 멈춤).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import variants_v11 as v11  # noqa: E402
import variants_v13 as v13  # noqa: E402

KIND = {"public-agentdojo-x4": "공개", "public-injecagent3": "공개", "public-agentdojo-x5": "공개",
        "ours13": "일반", "ours16": "일반", "ours18": "일반",
        "ours14": "적응형·짝", "ours15": "적응형·짝", "ours17": "적응형·짝", "ours19": "적응형·짝"}
UNSEEN = {  # 판 → [(묶음, 유리할 수 있음 사유 또는 "")]
    "v10": [("public-agentdojo-x4", ""), ("ours13", ""), ("ours15", ""), ("ours14", ""), ("public-injecagent3", ""),
            ("public-agentdojo-x5", ""), ("ours16", ""), ("ours17", ""), ("ours18", ""), ("ours19", "")],
    "v11": [("ours15", "시나리오 앎"), ("ours14", ""), ("public-injecagent3", ""), ("public-agentdojo-x5", ""),
            ("ours16", ""), ("ours17", ""), ("ours18", ""), ("ours19", "")],
    "v12": [("ours14", ""), ("public-injecagent3", ""), ("public-agentdojo-x5", ""), ("ours16", "시나리오 일부 읽음"),
            ("ours17", "기법 이름 읽음"), ("ours18", "같은 세션이 씀"), ("ours19", "같은 세션이 씀")],
    "v13": [("public-injecagent3", ""), ("public-agentdojo-x5", ""), ("ours16", "시나리오 일부 읽음"),
            ("ours17", "기법 이름 읽음"), ("ours18", "같은 세션이 씀"), ("ours19", "같은 세션이 씀 · v13을 읽고 피함")],
}


def main() -> int:
    cache = {}
    print("| 판 | 성격 | 묶음 | 공격 통과 | 정상 멈춤 | (같은 묶음 v3b) |")
    print("|---|---|---|---|---|---|")
    for pol, items in UNSEEN.items():
        for kind in ("공개", "일반", "적응형·짝"):
            names = [(n, w) for n, w in items if KIND[n] == kind and (ROOT / "runs" / f"attack-{n}-report.md").exists()
                     and (ROOT / "runs" / f"attack-{n}-v2-r3").exists()]
            if not names:
                continue
            a = na = s = nn = ba = bs = 0
            for n, _ in names:
                if n not in cache:
                    p = ROOT / "runs" / f"attack-{n}-v2-r3"
                    c = v13.count(p)
                    c["v10"] = v11.count(p)["v10"]
                    cache[n] = c
                c = cache[n]
                x, y, _z = c["v3b"]["n"]
                a += len(c[pol]["attack_passed"])
                na += x
                ba += len(c["v3b"]["attack_passed"])
                if y:
                    s += len(c[pol]["normal_stopped"])
                    bs += len(c["v3b"]["normal_stopped"])
                    nn += y
            label = " · ".join(n + (f"({w})" if w else "") for n, w in names)
            print(f"| {pol} | {kind} | {label} | {a}/{na} | " + (f"{s}/{nn}" if nn else "—") + f" | {ba}/{na} · " + (f"{bs}/{nn}" if nn else "—") + " |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
