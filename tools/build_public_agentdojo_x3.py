#!/usr/bin/env python3
"""공개 자료 묶음 3·4·5판 — AgentDojo(ethz-spylab/agentdojo, MIT) slack·banking·travel 공격만, 문구 틀만 바꿈

  python3 -I tools/build_public_agentdojo_x3.py <agentdojo 폴더> ignore_previous > attack/public-agentdojo-x3.json
  python3 -I tools/build_public_agentdojo_x3.py <agentdojo 폴더> system_message  > attack/public-agentdojo-x4.json
  python3 -I tools/build_public_agentdojo_x3.py <agentdojo 폴더> injecagent      > attack/public-agentdojo-x5.json   (11-20 05:3x 더함 · 2판 짝 · id A1341…)

1판(important_instructions · 1판 짝)·2판(direct · 2판 짝)과 같은 공격 목표 20개를 다른 문구 틀로 다시 잰다 — 「문구만 바꾸면 뚫리나」.
  ignore_previous → 1판 짝(build_public_agentdojo_x.py ATTACKS) · id A1301…
  system_message  → 2판 짝(build_public_agentdojo_x2.py ATTACKS2) · id A1321…
문구는 AgentDojo 소스(attacks/baseline_attacks.py IgnorePreviousAttack · SystemMessageAttack)의 __init__ 첫 인자를 ast로 읽고
build_public_agentdojo.py TEMPLATES 사본과 대조한다(원문 오타 「iunstructions」도 그대로). 정상 과업은 1·2판에서 다 썼으므로 없다(정상 대조 없음).
AgentDojo 코드는 실행하지 않는다(ast.parse·yaml.safe_load만 — 1판 빌더 그대로).
"""
from __future__ import annotations

import ast
import contextlib
import importlib.util
import io
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TPL = sys.argv[2]
assert TPL in ("ignore_previous", "system_message", "injecagent"), TPL
sys.argv = sys.argv[:2]


def load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    m = importlib.util.module_from_spec(spec)
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        spec.loader.exec_module(m)      # 앞 판 빌더 — JSON·요약 출력은 버리고 정의만 쓴다
    return m


X2 = load("adx2", "build_public_agentdojo_x2.py")
X = X2.X
B0 = load("ad0", "build_public_agentdojo.py")

CLS = {"ignore_previous": "IgnorePreviousAttack", "system_message": "SystemMessageAttack", "injecagent": "InjecAgentAttack"}[TPL]
t = ast.parse((X.ROOT / "attacks/baseline_attacks.py").read_text(encoding="utf-8"))
cls = next(c for c in t.body if isinstance(c, ast.ClassDef) and c.name == CLS)
JB = next(x.args[0].value for x in ast.walk(cls) if isinstance(x, ast.Call) and isinstance(x.func, ast.Attribute)
          and x.func.attr == "__init__" and x.args and isinstance(x.args[0], ast.Constant))
assert JB == B0.TEMPLATES[TPL], f"AgentDojo {TPL} 문구가 build_public_agentdojo.py 사본과 다르다: {JB!r}"
TECH = B0.TECH[TPL]

if TPL == "ignore_previous":
    PAIRS, START, PAN = X.ATTACKS, 1301, "1판 짝"
elif TPL == "system_message":
    PAIRS, START, PAN = X2.ATTACKS2, 1321, "2판 짝"
else:
    PAIRS, START, PAN = X2.ATTACKS2, 1341, "2판 짝"
PANNO = {1301: "3", 1321: "4", 1341: "5"}[START]
SET_NOTE = (f"공개 자료 — AgentDojo slack·banking·travel(MIT) {PANNO}판 · 문구 틀 {TPL} · {PAN} 그대로 · "
            "공격만(정상 대조 없음) · 문장 원문 그대로 · 짝짓기·인자 채우기는 우리가 함 · "
            + ("v7까지 안 본 자료" if START != 1341 else "v10 고정(8e4593b) 뒤에 만듦 — 공격 호출은 2판과 같음"))

out = []
for n, (suite, it, ut, vec) in enumerate(PAIRS, START):
    st = X.S[suite]
    raw, hit_i = st.ut[ut]["calls"], None
    for i in range(len(raw)):
        if X.kind_of(raw[i]["fn"]) != "read":
            break
        c = X.calls_of(suite, ut, i + 1)[i]
        if f"<<{vec}>>" in X.read_out(suite, c["fn"], c["args"]):
            hit_i = i
            break
    if hit_i is None:
        raise SystemExit(f"{suite} {ut}의 읽기에 주입 자리 {vec}가 없다")
    acts = X.calls_of(suite, ut, hit_i + 1)
    hit = acts[-1]
    icalls_all = st.it[it]["calls"]
    idx = next((i for i, c in enumerate(icalls_all) if X.kind_of(c["fn"]) == "state"), len(icalls_all) - 1)
    icalls = X.calls_of(suite, it, idx + 1)
    call = icalls[idx]
    goal = st.it[it]["text"]
    src = f"[{X.call_str(hit)}]\n" + st.fill(X.read_out(suite, hit["fn"], hit["args"]), {vec: JB.format(goal=goal)})
    if len(src) > 4000:
        raise SystemExit(f"A{n}: source_text {len(src)}자")
    tool = {"name": X.RENAME.get(call["fn"], call["fn"]), "args": call["args"]}
    why = [f"{suite} {it}(공격 목표 원문 · AgentDojo {st.it[it]['ver']}) × {ut}(사용자 과업 원문 · {st.ut[ut]['ver']})",
           f"주입 자리 {vec} — {X.call_str(hit)}이 돌려주는 글에 있음(정적 확인) · 문구 틀 {TPL}({JB!r}) · {PAN} · 짝짓기는 우리가 함",
           f"tool_call = 공격 목표 정답 호출의 첫 상태 변경 호출 {call['fn']}" if X.kind_of(call["fn"]) == "state"
           else f"tool_call = 공격 목표 정답 호출이 읽기 {call['fn']} 하나뿐이라 그것을 씀(상태 변경 호출 없음)"]
    if tool["name"] != call["fn"]:
        why.append(f"도구 이름만 {call['fn']}→{tool['name']}")
    why.append(X.describe_call(call))
    if idx:
        why.append(f"actions_so_far = 사용자 과업의 정답 읽기 {len(acts)}건(주입된 글을 받는 읽기까지) + 공격 목표 정답의 앞선 읽기 {idx}건")
    why += [x for x in (X.describe_reads(acts), X.describe_reads(icalls[:idx])) if x]
    out.append({
        "id": f"A{n}", "kind": "attack", "expect": "BLOCK",
        "origin": "AgentDojo", "origin_url": st.it[it]["url"], "license": X.LICENSE, "technique": TECH,
        "set_note": SET_NOTE, "why": " · ".join(why),
        "user_request": st.ut[ut]["text"],
        "actions_so_far": [X.call_str(c) for c in acts] + [X.call_str(c) for c in icalls[:idx]],
        "tool_call": tool, "source_text": src,
    })

json.dump(out, sys.stdout, ensure_ascii=False, indent=1)
print()
print(f"{TPL}: {len(out)}건 · 문구 {JB!r} · {PAN}", file=sys.stderr)
