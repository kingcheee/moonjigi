"""플레이그라운드용 v14 실시간 판정(11-20 hackathon-38 · 사용자 「플레이그라운드를 v14로」).

v14는 밤새 공격 측정에서 v2 기록 위에 계산하던 후보 판이다(`variants_v14.py` · 1d8345c 07:12 고정 · `1e9b7246f298`).
여기서는 같은 계산을 실시간으로 한다: 판정 서버에 v2 질문을 그대로 묻고(직답) → v14 결정 함수에 넣는다.
v14가 추론을 원하면(v5 단계 「MISSING」) needs_reason으로 돌려주고, /gate/reason에서 v2 추론을 묻은 뒤 다시 v14에 넣는다.
결정 코드는 variants_v14.decide_v14 그대로다 — 이 파일은 기록 모양(verdict)을 맞추고 시간 제한·회사 규칙만 더한다.

- 추론 시간 제한: gate.REASON_TIMEOUT_S(60초). 넘거나 오류면 추론 기록 없이 cut으로 남기고 v5가 사람 확인으로 돌린다(측정과 같은 규칙).
- 회사 규칙(rules=["pii"]): v2 직답에서 규칙이 걸리면 v14 결정보다 엄한 쪽을 쓴다(규칙은 멈추는 데만 쓴다 — gate.apply_rules와 같은 원칙).
- 무대 장면(index)·운영 콘솔은 서버 기본 판(v3) 그대로다. 요청 body에 "policy": "v14"가 있을 때만 이 길로 온다.
"""
from __future__ import annotations

import time

import gate
import variants_v14 as v14

NAME = "v14"
VERSION = v14.V14_VERSION
STRICT = {"PASS": 0, "MISSING": 1, "REASON": 1, "CONFIRM": 2, "BLOCK": 3}


def _scenario(call: dict) -> dict:
    return {"user_request": call.get("user_request") or "", "actions_so_far": call.get("actions_so_far") or [],
            "tool_call": call.get("tool_call") or {}, "source_text": call.get("source_text") or ""}


def _decide(v: dict, call: dict) -> tuple[str, str]:
    return v14.decide_v14({"id": "live", "kind": "live", "verdict": v}, _scenario(call))


def _rule_hit(v: dict) -> dict | None:
    return next((x for x in v.get("rules") or [] if x.get("hit")), None)


def _wrap(v: dict, dec: str, rule: str) -> dict:
    hit = _rule_hit(v)
    if hit and STRICT.get(dec, 0) < STRICT["CONFIRM"]:
        dec, rule = "CONFIRM", f"company rule: {hit['id']} >={hit['threshold']}"
    out = dict(v)
    reasoned = "reasoned" in (v.get("ms") or {})
    if dec == "MISSING":
        out.update(decision="REASON", rule="no rule fired", needs_reason=True, stage="direct")
    else:
        out.update(decision=dec, rule=rule, needs_reason=False,
                   stage="human" if dec == "CONFIRM" and reasoned else ("reasoned" if reasoned else "direct"))
    out.update(policy=NAME, policy_version=VERSION, base_policy="v2", base_policy_version=gate.POLICY_VERSIONS["v2"],
               base_decision=v.get("decision"))
    return out


def direct(url: str, call: dict, rules: list | None = None) -> dict:
    v = gate.check_direct(url, call, "v2", rules)
    v["ms"]["total"] = v["ms"]["direct"]
    dec, rule = _decide(v, call)                # 규칙이 걸렸으면 _wrap이 MISSING도 CONFIRM으로 올린다 — 추론을 기다리지 않는다
    out = _wrap(v, dec, rule)
    out["_v2"] = v                              # /gate/reason이 v2 기록 위에 추론을 잇는다(응답 전에 server가 뺀다)
    return out


def reason(url: str, call: dict, v14_direct: dict) -> dict:
    v0 = v14_direct.get("_v2") or v14_direct
    t0 = time.perf_counter()
    v = dict(v0)
    try:
        data, ms = gate.ask(url, call, reasoning=True, pv="v2", timeout=gate.REASON_TIMEOUT_S)
        p = gate.to_probs(data["answers"], call, "v2")
        v.update(reasoned=p, answers_source=data.get("answers_source"), cut=data.get("cut"),
                 reasoning_tokens=(data.get("usage") or {}).get("output_tokens"),
                 reasoning=(data.get("reasoning") or "")[:2000])
    except Exception as e:
        ms = (time.perf_counter() - t0) * 1000
        v.update(cut=f"timeout/error: {type(e).__name__}", reasoning="", error=str(e)[:300])
    v["ms"] = dict(v0["ms"], reasoned=round(ms, 1))
    v["ms"]["total"] = round(v0["ms"]["direct"] + ms, 1)
    dec, rule = _decide(v, call)
    if dec == "MISSING":                        # 추론 기록이 있는데도 모자라면 사람 확인(불리한 쪽)
        dec, rule = "CONFIRM", "reasoning cut/timeout -> human"
    return _wrap(v, dec, rule)
