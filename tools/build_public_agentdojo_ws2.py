#!/usr/bin/env python3
"""공개 자료 묶음 — AgentDojo(MIT) workspace 2판: 1판 공격 목표를 다른 문구 틀 둘로 다시 → attack/public-agentdojo-ws2.json (11-20 hackathon-fd)

  python3 -I tools/build_public_agentdojo_ws2.py <agentdojo 폴더> > attack/public-agentdojo-ws2.json

1판(build_public_agentdojo.py · important_instructions)의 공격 목표 14개 중 1판에서 이미 문구 틀 다섯 가지를 다 잰 InjectionTask1 · 4를 뺀
12개를 system_message · injecagent 두 틀로 다시 쓴다(공격 24 · id A1361…). 사용자 과업 · 주입 자리 · 노리는 호출 · 앞선 동작은 1판 짝 그대로.
문구 틀 원문은 1판 빌더 TEMPLATES 사본(AgentDojo attacks/baseline_attacks.py SystemMessageAttack · InjecAgentAttack)을 그대로 쓴다.
정상 과업은 1판에서 다 썼으므로 없다(정상 대조 없음). AgentDojo 코드는 실행하지 않는다(1판 빌더 그대로 — YAML · 문자열만 읽음).
v13 고정(86d6923 06:22) 뒤에 만들었다 — 판 기준으로는 안 본 자료. 다만 workspace 공격 목표 자체는 1판 결과(11-19)로 봤다.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("ad0", HERE / "build_public_agentdojo.py")
B0 = importlib.util.module_from_spec(spec)
with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
    spec.loader.exec_module(B0)       # 1판 빌더 — JSON 출력은 버리고 정의만 쓴다

TPLS = ["system_message", "injecagent"]
SET_NOTE = ("공개 자료 — AgentDojo workspace(MIT) 2판 · 1판 공격 목표 12개(InjectionTask1 · 4 뺌)를 문구 틀 system_message · injecagent로 다시 · "
            "사용자 과업 · 공격 목표 · 문구 틀 · 메일 · 일정 · 파일 본문 원문 그대로 · 짝짓기 · 도구 이름 옮김은 우리가 함(1판 그대로) · v13 고정 뒤에 만듦")
out = []
n = 1360
for tpl in TPLS:
    for it, ut, sk, call in B0.ATTACKS:
        if it in ("InjectionTask1", "InjectionTask4"):
            continue
        n += 1
        vec, fn, acts = B0.src[sk]
        out.append({
            "id": f"A{n}", "kind": "attack", "expect": "BLOCK",
            "origin": "AgentDojo", "origin_url": f"{B0.URL}/default_suites/v1/workspace", "license": B0.LICENSE,
            "technique": B0.TECH[tpl], "set_note": SET_NOTE,
            "why": f"{it}(공격 목표 원문) × UserTask{ut}(사용자 과업 원문) · 주입 자리 {vec} · 문구 틀 {tpl} — 1판 짝 그대로 · 짝짓기·도구 이름 옮김은 우리가 함",
            "user_request": B0.prompt(ut), "actions_so_far": acts, "tool_call": call,
            "source_text": fn({vec: B0.attack_text(tpl, B0.IT[it]["GOAL"])}),
        })
json.dump(out, sys.stdout, ensure_ascii=False, indent=1)
print()
