#!/usr/bin/env python3
"""공격 측정 시나리오 모양 검사 — 판정 서버를 부르지 않는다(unseen_all.sh의 검사와 같은 기준 + 출처 칸).

  python3 tools/attack_check.py attack/<파일>.json

칸: id · kind(normal/attack/ambiguous) · expect(PASS/CONFIRM/BLOCK) · user_request · actions_so_far(목록) ·
    tool_call{name,args} · source_text(글) · origin(누가 썼나 — ours / 공개 자료 이름) · technique(공격 기법 이름, 정상은 비움)
공개 자료에서 옮긴 건은 origin_url · license를 함께 적는다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import gate  # noqa: E402

path = Path(sys.argv[1])
d = json.loads(path.read_text(encoding="utf-8"))
assert isinstance(d, list), "시나리오 파일은 목록이어야 한다"
bad, kinds, origins = [], {}, {}
ids = [x.get("id") for x in d]
if len(set(ids)) != len(ids):
    bad.append("id 중복: " + ", ".join(sorted({str(i) for i in ids if ids.count(i) > 1})))
for x in d:
    i = x.get("id")
    for k in ("id", "kind", "expect", "user_request", "tool_call", "origin"):
        if not x.get(k):
            bad.append(f"{i}: {k} 없음")
    if x.get("kind") not in ("normal", "attack", "ambiguous"):
        bad.append(f"{i}: kind={x.get('kind')}")
    if x.get("expect") not in ("PASS", "CONFIRM", "BLOCK"):
        bad.append(f"{i}: expect={x.get('expect')}")
    if x.get("kind") == "attack" and not x.get("technique"):
        bad.append(f"{i}: 공격인데 technique 없음")
    if x.get("origin") not in (None, "", "ours") and not (x.get("origin_url") and x.get("license")):
        bad.append(f"{i}: 공개 자료(origin={x.get('origin')})인데 origin_url·license 없음")
    tc = x.get("tool_call") or {}
    if not isinstance(tc, dict) or not tc.get("name") or not isinstance(tc.get("args", {}), dict):
        bad.append(f"{i}: tool_call 모양")
    if not isinstance(x.get("actions_so_far", []), list) or not all(isinstance(a, str) for a in x.get("actions_so_far", [])):
        bad.append(f"{i}: actions_so_far는 글 목록")
    if not isinstance(x.get("source_text", ""), str):
        bad.append(f"{i}: source_text는 글")
    call = {"user_request": x.get("user_request", ""), "actions_so_far": x.get("actions_so_far") or [], "tool_call": tc}
    if x.get("source_text"):
        call["source_text"] = x["source_text"]
    try:
        for pv in ("v1", "v2"):
            json.dumps({"state": gate.build_state(call), "questions": {**gate.questions_for(call, pv), **gate.rule_questions(call, ["pii"])}}, ensure_ascii=False)
    except Exception as e:  # noqa: BLE001
        bad.append(f"{i}: 요청을 못 만든다 — {type(e).__name__}: {e}")
    kinds[x.get("kind")] = kinds.get(x.get("kind"), 0) + 1
    origins[x.get("origin")] = origins.get(x.get("origin"), 0) + 1
if bad:
    sys.exit("시나리오 모양 오류:\n  " + "\n  ".join(bad))
long = [x["id"] for x in d if len(x.get("source_text") or "") > gate.SOURCE_MAX_CHARS]
print(f"{path.name}: {len(d)}건 · 종류 {kinds} · 출처 {origins}" + (f" · source_text {gate.SOURCE_MAX_CHARS}자 넘어 잘리는 건 {long}" if long else ""))
