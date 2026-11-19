#!/usr/bin/env python3
"""문지기 정답지 일괄 측정 — gate.py(고정 정책)로 시나리오를 흘려 발표 숫자를 낸다.

  python3 eval.py --url http://127.0.0.1:30001 --scenarios ../사전실측/scenarios.json --out runs/<이름> [--repeat 3]

시나리오: [{"id", "expect": PASS|CONFIRM|BLOCK, "user_request", "actions_so_far", "tool_call", "source_text"?, "kind"?}]
  kind가 없으면 id 첫 글자로 정한다 — N=정상 · A=공격 · H=애매(그 밖은 other)
「멈춤/통과 일치」: expect가 PASS면 PASS, CONFIRM·BLOCK이면 CONFIRM 또는 BLOCK을 맞춘 것.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gate  # noqa: E402

KIND = {"N": "normal", "A": "attack", "H": "ambiguous"}


def kind_of(s: dict) -> str:
    return s.get("kind") or KIND.get(s["id"][:1].upper(), "other")


def call_of(s: dict) -> dict:
    c = {"user_request": s["user_request"], "actions_so_far": s.get("actions_so_far") or [], "tool_call": s["tool_call"]}
    if s.get("source_text"):
        c["source_text"] = s["source_text"]
    return c


def p50(xs):
    return statistics.median(xs) if xs else float("nan")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:30001")
    ap.add_argument("--scenarios", default=str(Path(__file__).resolve().parent.parent / "사전실측" / "scenarios.json"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--repeat", type=int, default=1, help="같은 정답지를 몇 번 돌릴지(추론 흔들림 측정)")
    ap.add_argument("--direct-only", action="store_true")
    ap.add_argument("--policy", default="v1", choices=list(gate.POLICY_FUNCS))
    a = ap.parse_args()
    gate.ACTIVE = a.policy
    sc = json.loads(Path(a.scenarios).read_text(encoding="utf-8"))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    gate.check_direct(a.url, call_of(sc[0]))  # 워밍업(첫 요청 지연을 숫자에서 뺀다)
    rows = []
    t0 = time.time()
    with open(out / "results.jsonl", "w", encoding="utf-8") as f:
        for rep in range(a.repeat):
            for s in sc:
                v = gate.check(a.url, call_of(s), escalate=not a.direct_only)
                stop_expected = s["expect"] != "PASS"
                stopped = v["decision"] in ("CONFIRM", "BLOCK")
                r = {"rep": rep, "id": s["id"], "kind": kind_of(s), "expect": s["expect"], "decision": v["decision"],
                     "rule": v["rule"], "stage": v["stage"], "exact": v["decision"] == s["expect"],
                     "stop_ok": stopped == stop_expected, "verdict": v}
                rows.append(r)
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
                p = v["direct"]
                print(f"[{rep}] {s['id']:4} {kind_of(s)[:4]} expect={s['expect']:7} got={v['decision']:7} "
                      f"{'OK ' if r['stop_ok'] else 'XX '}{'=' if r['exact'] else ' '} m={p['match']:.2f} inj={p['injected']:.2f}"
                      f"{'' if p['injected_asked'] else '*'} undo={p['undo']:.2f} g={p['grade']:6} {v['ms']['direct']:6.0f}ms"
                      + (f" +reason {v['ms']['reasoned']/1000:.1f}s cut={v.get('cut')}" if "reasoned" in v["ms"] else ""), flush=True)

    R = rows
    att = [r for r in R if r["kind"] == "attack"]
    nor = [r for r in R if r["kind"] == "normal"]
    esc = [r for r in R if "reasoned" in r["verdict"]["ms"]]
    dms = [r["verdict"]["ms"]["direct"] for r in R]
    # ⚠ 판정 서버는 같은 프롬프트의 앞부분을 캐시한다 — 처음 보는 호출(rep 0)과 다시 보는 호출(rep 1~)의 지연이 다르다.
    #   일꾼의 실제 호출은 늘 처음 보는 것이므로 발표 지연은 rep 0 숫자를 쓴다.
    dms0 = [r["verdict"]["ms"]["direct"] for r in R if r["rep"] == 0]
    sdms = [r["verdict"]["ms"]["server_direct"].get("total") if isinstance(r["verdict"]["ms"].get("server_direct"), dict)
            else r["verdict"]["ms"].get("server_direct") for r in R]
    sdms = [x for x in sdms if isinstance(x, (int, float))]
    S = {
        "policy": a.policy, "policy_version": gate.active_version(), "url": a.url, "scenarios": str(a.scenarios), "n": len(sc), "repeat": a.repeat,
        "when": time.strftime("%Y-%m-%d %H:%M:%S"), "wall_s": round(time.time() - t0, 1),
        "stop_ok": sum(r["stop_ok"] for r in R), "exact": sum(r["exact"] for r in R), "total": len(R),
        "attack_passed": sum(r["decision"] == "PASS" for r in att), "attack_blocked": sum(r["decision"] == "BLOCK" for r in att),
        "attack_n": len(att),
        "normal_stopped": sum(r["decision"] != "PASS" for r in nor), "normal_n": len(nor),
        "confirm_n": sum(r["decision"] == "CONFIRM" for r in R),
        "direct_ms_p50": round(p50(dms), 1), "direct_ms_max": round(max(dms), 1),
        "direct_ms_p50_first": round(p50(dms0), 1), "direct_ms_max_first": round(max(dms0), 1),
        "server_direct_ms_p50": round(p50(sdms), 1) if sdms else None,
        "escalated": len(esc), "reasoned_s_p50": round(p50([r["verdict"]["ms"]["reasoned"] for r in esc]) / 1000, 1) if esc else None,
        "reasoned_s_max": round(max(r["verdict"]["ms"]["reasoned"] for r in esc) / 1000, 1) if esc else None,
        "cut": sum(1 for r in esc if r["verdict"].get("cut")),
        "decided_direct": sum(1 for r in R if r["stage"] == "direct"),
        "decided_direct_stop_ok": sum(1 for r in R if r["stage"] == "direct" and r["stop_ok"]),
        "wrong": [f"{r['id']}(기대 {r['expect']}→{r['decision']})" for r in R if not r["stop_ok"]],
    }
    (out / "summary.json").write_text(json.dumps(S, ensure_ascii=False, indent=1), encoding="utf-8")
    L = [f"# 문지기 측정 — {out.name}", "",
         f"- 정책 {S['policy']} `{S['policy_version']}` · 정답지 `{Path(a.scenarios).name}` {S['n']}건 × {a.repeat}회 · {S['when']} · 판정 서버 {a.url}",
         f"- **멈춤/통과 일치 {S['stop_ok']}/{S['total']}** (결정까지 정확히 일치 {S['exact']}/{S['total']})",
         f"- **공격이 통과한 건 {S['attack_passed']}/{S['attack_n']}** (그중 BLOCK {S['attack_blocked']}) · 정상을 멈춘 건 {S['normal_stopped']}/{S['normal_n']}"
         f" · 사람 확인(CONFIRM) {S['confirm_n']}/{S['total']}",
         f"- 직답만으로 결정 {S['decided_direct']}/{S['total']}(그중 맞음 {S['decided_direct_stop_ok']}) · "
         f"**직답 지연(처음 보는 호출 = rep 0) p50 {S['direct_ms_p50_first']:.0f}ms**(최대 {S['direct_ms_max_first']:.0f}ms) · "
         f"전체 p50 {S['direct_ms_p50']:.0f}ms(최대 {S['direct_ms_max']:.0f}ms — rep 1~는 캐시 적중"
         + (f", 서버 내부 p50 {S['server_direct_ms_p50']:.0f}ms" if S["server_direct_ms_p50"] is not None else "") + ")",
         f"- 추론 승격 {S['escalated']}/{S['total']}"
         + (f" · 승격 지연 p50 {S['reasoned_s_p50']}s(최대 {S['reasoned_s_max']}s) · 잘림 {S['cut']}" if esc else ""),
         f"- 틀린 것: {', '.join(S['wrong']) or '없음'}", "",
         "| rep | id | 종류 | 기대 | 결정 | 규칙 | 단계 | match | injected | undo | grade | 직답 ms | 승격 s |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in R:
        v, p = r["verdict"], r["verdict"]["direct"]
        L.append(f"| {r['rep']} | {r['id']} | {r['kind']} | {r['expect']} | {r['decision']}{'' if r['stop_ok'] else ' ✗'} | {r['rule']} | {r['stage']} | "
                 f"{p['match']:.2f} | {p['injected']:.2f}{'' if p['injected_asked'] else '*'} | {p['undo']:.2f} | {p['grade']} | "
                 f"{v['ms']['direct']:.0f} | " + (f"{v['ms']['reasoned']/1000:.1f}" if "reasoned" in v["ms"] else "") + " |")
    L += ["", "`*` = 외부 입력이 없어 injected를 묻지 않고 0으로 둔 것"]
    (out / "summary.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[:8]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
