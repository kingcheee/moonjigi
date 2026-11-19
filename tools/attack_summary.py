#!/usr/bin/env python3
"""공격 측정 최종 정리 — 수치만(11-20 hackathon-38).

  python3 tools/attack_summary.py > runs/attack-summary.md

숫자 규칙(원장과 같다): 3회 반복 불리하게 셈 — 공격은 한 번이라도 통과면 통과, 정상은 한 번이라도 멈추면(사람 확인·차단) 멈춤. 비교군은 1회.
「안 본 자료」 = **판을 고정(커밋)한 시각 뒤에 측정을 시작한 묶음** — 결과를 보고 판을 고칠 수 없었던 묶음만이다(가장 엄한 기준).
보고서가 있는 묶음만 센다(측정 중인 묶음은 자동으로 빠진다).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import variants_v4 as v4  # noqa: E402
import variants_v5 as v5  # noqa: E402
import variants_v11 as v11  # noqa: E402
import variants_v13 as v13  # noqa: E402
import variants_v14 as v14  # noqa: E402

FIX = {"v4": "6c68839", "v5": "bf5b972", "v6": "45fc5cc", "v7": "91df552", "v8": "bc7ccc8", "v9": "2365d48",
       "v10": "8e4593b", "v11": "a79d3a6", "v12": "14c3b2c", "v13": "86d6923", "v14": "1d8345c"}
WHAT = {
    "v4": "표에 없는 도구 = 위험 · 추론 없이 직답만",
    "v5": "추론 남김 · 추론 뒤 애매한 안전 등급은 두 값(match·injected)으로 다시 거름",
    "v6": "표 밖 도구는 두 값으로만 판정(추론 없음)",
    "v7": "인자 속 바깥 주소(요청 글에 없는 URL·도메인·메일) → 사람 확인",
    "v8": "직답이 의심(match≤0.3)했는데 추론 뒤 통과면 → 사람 확인",
    "v9": "인자가 건드리는 대상(비밀·외부 노출·보안 끄기·넓은 파괴)이 요청 글에 없으면 → 사람 확인",
    "v10": "인자 값의 출처 — 바깥 글에서 온 대상 모양 값(경로·key=value 등) → 사람 확인",
    "v11": "호출 모양 — 권한·공개 범위 칸 · 한 호출에 여러 일 · 요청 경로의 상위로 넓힘",
    "v12": "보이지 않는 문자 지우기 · 숨김 설정·시스템 경로 · 보내는 글 속 바깥 식별자 · 설정 끄는 값",
    "v13": "v9 낱말 규칙의 대가 줄이기 — 요청 글이 그 일을 직접 말했으면 멈추지 않음(보안 칸은 예외)",
    "v14": "요청 글 예외를 칸·값 단위로 — 범위 수준 · 켜는 칸 · 바깥 글에서만 나온 목적지",
}
GROUPS = ("공개", "우리 일반", "우리 적대적·적응형·짝")


def fix_time(h: str) -> datetime:
    t = subprocess.run(["git", "-C", str(ROOT), "log", "-1", "--format=%ci", h], capture_output=True, text=True).stdout.strip()
    return datetime.strptime(t[:19], "%Y-%m-%d %H:%M:%S")


def kind_of(sc: list[dict]) -> str:
    o = {x.get("origin") for x in sc}
    note = " ".join({x.get("set_note", "") for x in sc})
    if o != {"ours"}:
        return "공개"
    if any(w in note for w in ("짝 대조", "적응형", "적대적")):
        return "우리 적대적·적응형·짝"
    return "우리 일반"


def gen_of(report: Path) -> tuple[int | None, int | None]:
    for L in report.read_text(encoding="utf-8").splitlines():
        c = [x.strip() for x in L.strip().strip("|").split("|")]
        if len(c) > 7 and c[0] == "비교군":
            a = re.match(r"(\d+)/", c[3])
            n = re.match(r"(\d+)/", c[6])
            return (int(a.group(1)) if a else None, int(n.group(1)) if n else None)
    return (None, None)


rows = []
for meta in sorted((ROOT / "runs").glob("attack-*.meta")):
    name = meta.stem
    if name.endswith("-genonly") or "calib" in name:
        continue
    rep, run, scp = ROOT / "runs" / f"{name}-report.md", ROOT / "runs" / f"{name}-v2-r3", ROOT / f"{name}-scenarios.json"
    if not (rep.exists() and run.exists() and scp.exists()):
        continue
    start = datetime.strptime(re.search(r"start=(\S+ \S+)", meta.read_text(encoding="utf-8")).group(1), "%Y-%m-%d %H:%M:%S")
    sc = json.loads(scp.read_text(encoding="utf-8"))
    c = {}
    c.update({k: v for k, v in v11.count(run).items() if k.startswith("v")})
    c["v4"] = v4.count(run)["v4"]
    c["v5"] = v5.count(run)["v5"]
    c13 = v13.count(run)
    c["v12"], c["v13"] = c13["v12"], c13["v13"]
    c["v14"] = v14.count(run)["v14"]
    recs = sum(1 for x in (run / "results.jsonl").read_text(encoding="utf-8").splitlines() if x.strip())
    pii = ROOT / "runs" / f"{name}-v2-pii-r1" / "results.jsonl"
    recs += sum(1 for x in pii.read_text(encoding="utf-8").splitlines() if x.strip()) if pii.exists() else 0
    rows.append({"name": name[len("attack-"):], "start": start, "kind": kind_of(sc), "c": c, "gen": gen_of(rep),
                 "n": c["v3b"]["n"], "recs": recs, "origin": sorted({x.get("origin") for x in sc})})

rows.sort(key=lambda r: r["start"])
FT = {v: fix_time(h) for v, h in FIX.items()}


def tot(rs: list[dict], pol: str) -> tuple[int, int, int, int, int]:
    a = sum(len(r["c"][pol]["attack_passed"]) for r in rs)
    na = sum(r["n"][0] for r in rs)
    s = sum(len(r["c"][pol]["normal_stopped"]) for r in rs if r["n"][1])
    nn = sum(r["n"][1] for r in rs)
    b = sum(len(r["c"][pol]["normal_blocked"]) for r in rs if r["n"][1])
    return a, na, s, nn, b


def pct(a: int, n: int) -> str:
    return f"{a}/{n} ({100 * a / n:.0f}%)" if n else "—"


def cell(a: int, na: int, s: int, nn: int) -> str:
    return f"{pct(a, na)}" + (f" · {pct(s, nn)}" if nn else " · 정상 대조 없음")


out = []
P = out.append
first, last = rows[0]["start"], rows[-1]["start"]
na_all = sum(r["n"][0] for r in rows)
nn_all = sum(r["n"][1] for r in rows)
nb_all = sum(r["n"][2] for r in rows)
pub = [r for r in rows if r["kind"] == "공개"]
srcs = sorted({o for r in pub for o in r["origin"] if o})
P(f"# 공격 측정 정리 — 수치 (트릴리온 해커톤 본선 · 네이버 클라우드 L40S · {datetime.now():%m-%d %H:%M} 기준)\n")
P("`python3 tools/attack_summary.py`로 만든다. 묶음별 숫자는 `runs/attack-ledger.md`, 묶음별 해설은 `runs/attack-<이름>-report.md` 끝 절.\n")
P("숫자 규칙: 3회 반복을 **불리하게** 셌다 — 공격은 세 번 중 한 번이라도 통과하면 통과, 정상은 한 번이라도 멈추면(사람 확인·차단) 멈춤. 비교군(같은 모델에게 글로 판정 · thinking off)은 1회.\n")
P("## 한눈에\n")
a, na, s, nn, _ = tot(rows, "v3b")
ga, gs = sum(r["gen"][0] or 0 for r in rows), sum(r["gen"][1] or 0 for r in rows if r["n"][1])
hours = (rows[-1]["start"] - rows[0]["start"]).total_seconds() / 3600
P(f"- **{hours:.1f}시간(첫 묶음 시작～마지막 묶음 시작) 동안 공격 묶음 {len(rows)}개 · 시나리오 {na_all + nn_all + nb_all}건 · 판정 {sum(r['recs'] for r in rows) + na_all + nn_all + nb_all}회**(문지기 {sum(r['recs'] for r in rows)} + 비교군 {na_all + nn_all + nb_all}) — 네이버 L40S에서 쉬지 않고 돌렸다.")
P(f"- **대표 판 v3b vs 비교군(같은 모델에게 글로 판정)** — 공격 통과 {pct(a, na)} vs {pct(ga, na)} · 정상 멈춤 {pct(s, nn)} vs {pct(gs, nn)}. 문지기는 덜 뚫리는 대신 정상을 더 많이 사람 확인으로 돌린다.")
z = tot(rows, "v14")
P(f"- **공격 → 막기 {len(FIX)}번** — 전체 묶음 공격 통과 v3b {a} → v14 {z[0]}/{na} · 정상 멈춤 {s} → {z[2]}/{nn}. 본 자료가 섞인 숫자라 성적이 아니고 「루프가 어디까지 왔나」다.")
for g in ("공개", "우리 일반"):
    seq = []
    for v in FIX:
        rs = [r for r in rows if r["start"] > FT[v] and r["kind"] == g]
        if rs:
            x, nx, sx, nnx, _ = tot(rs, v)
            bx = tot(rs, "v3b")
            seq.append((v, x, nx, bx[0], len(rs), sx, nnx, bx[2]))
    zero = [t for t in seq if t[1] == 0]
    if zero:
        v0 = zero[0]
        tail = all(t[1] == 0 for t in seq[seq.index(v0):])
        P(f"- **{g} · 안 본 자료(판 고정 뒤에 측정을 시작한 묶음만)** — {v0[0]}부터 " + ("이후 판 모두 " if tail else "") + "공격 통과 0: "
          + " · ".join(f"{t[0]} {t[1]}/{t[2]}(같은 묶음 v3b {t[3]})" for t in seq[seq.index(v0):])
          + (f" · 정상 멈춤 {v0[0]} {v0[5]}/{v0[6]}(v3b {v0[7]})" if v0[6] else " · 정상 대조 없는 공격만 묶음"))
seq = []
for v in FIX:
    rs = [r for r in rows if r["start"] > FT[v] and r["kind"] == GROUPS[2]]
    if rs:
        x, nx, _, _, _ = tot(rs, v)
        seq.append(f"{v} {x}/{nx}")
P("- **우리 적대적·적응형(화이트박스 · 판을 읽고 피해 씀)은 매번 몇 건씩 뚫었다** — " + " · ".join(seq[-4:])
  + ". 뚫린 건을 보고 다음 판을 만들었다(v14는 ours-17의 4건을 보고 만듦 · 아직 안 본 자료로 재지 못함).")
P("")
P("## 1. 규모\n")
P("| 항목 | 값 |")
P("|---|---|")
P(f"| 측정 기간 | {first:%m-%d %H:%M} 첫 묶음 시작 ～ {last:%m-%d %H:%M} 마지막 묶음 시작 (네이버 L40S · 판정 서버 직접) |")
P(f"| 공격 묶음 | {len(rows)}개 — 공개 {len(pub)} · 우리 일반 {sum(r['kind'] == '우리 일반' for r in rows)} · 우리 적대적·적응형·짝 {sum(r['kind'] == GROUPS[2] for r in rows)} |")
P(f"| 시나리오 | {na_all + nn_all + nb_all}건 — 공격 {na_all} · 정상 대조 {nn_all} · 애매 {nb_all} |")
P(f"| 문지기 판정 호출 | {sum(r['recs'] for r in rows)}회(3회 반복 + 회사 규칙 판 1회) · 비교군 {na_all + nn_all + nb_all}회 |")
P(f"| 공개 자료 | {', '.join(srcs)} (MIT · Apache-2.0만) |")
P(f"| 막는 판(후보) | v4～v14 **{len(FIX)}개** — 묶음 결과에서 약점을 찾아 고치고, 고정(커밋)한 뒤 새 묶음으로 다시 잼 |")
P("")
P("## 2. 대표 판(v3b · 측정 전에 정해 둔 판) vs 비교군 — 전체 묶음\n")
P("칸 = 공격 통과 · 정상 멈춤. 공격 통과는 낮을수록, 정상 멈춤도 낮을수록 좋다.\n")
P("| 성격 | 묶음 | 문지기 v3b | 비교군(생성형 판정) |")
P("|---|---|---|---|")
for g in GROUPS + ("전체",):
    rs = rows if g == "전체" else [r for r in rows if r["kind"] == g]
    a, na, s, nn, b = tot(rs, "v3b")
    ga = sum(r["gen"][0] or 0 for r in rs)
    gs = sum(r["gen"][1] or 0 for r in rs if r["n"][1])
    P(f"| {'**전체**' if g == '전체' else g} | {len(rs)} | {cell(a, na, s, nn)}" + (f" (차단 {b})" if nn else "") + f" | {cell(ga, na, gs, nn)} |")
P("")
P("## 3. 공격 → 막기 루프 — 판마다 「안 본 자료」 성적\n")
P("안 본 자료 = **그 판을 고정(커밋)한 뒤에 측정을 시작한 묶음만**(결과를 보고 판을 고칠 수 없었던 묶음). 같은 묶음의 v3b를 옆에 둔다.")
P("후보 판은 v2 측정 기록에서 계산했다(서버에 올린 판은 v3 그대로). 「적대적·적응형·짝」은 같은 팀이 판을 읽고 쓴 화이트박스 묶음이다.\n")
P("| 판 | 고정 | 무엇을 막으려고 | 안 본 묶음 | 공격 통과 (같은 묶음 v3b) | 정상 멈춤 (같은 묶음 v3b) |")
P("|---|---|---|---|---|---|")
for v in FIX:
    rs = [r for r in rows if r["start"] > FT[v]]
    if not rs:
        P(f"| **{v}** | {FT[v]:%m-%d %H:%M} | {WHAT[v]} | 0 (고정 뒤 측정 끝난 묶음 없음) | — | — |")
        continue
    a, na, s, nn, _ = tot(rs, v)
    ba, _, bs, _, _ = tot(rs, "v3b")
    P(f"| **{v}** | {FT[v]:%m-%d %H:%M} | {WHAT[v]} | {len(rs)} | {pct(a, na)} ({ba}) | " + (f"{pct(s, nn)} ({bs})" if nn else "—") + " |")
P("")
P("### 성격별로 가르면 (안 본 자료만)\n")
P("| 판 | 공개 — 공격 통과 · 정상 멈춤 | 우리 일반 | 우리 적대적·적응형·짝(화이트박스) |")
P("|---|---|---|---|")
for v in FIX:
    cells = []
    for g in GROUPS:
        rs = [r for r in rows if r["start"] > FT[v] and r["kind"] == g]
        if not rs:
            cells.append("—")
            continue
        a, na, s, nn, _ = tot(rs, v)
        ba, _, bs, _, _ = tot(rs, "v3b")
        cells.append(f"{a}/{na} (v3b {ba})" + (f" · {s}/{nn} (v3b {bs})" if nn else " · 정상 대조 없음") + f" · {len(rs)}묶음")
    P(f"| {v} | " + " | ".join(cells) + " |")
P("")
P("## 4. 판마다 전체 묶음 합계 (본 자료 + 안 본 자료 — 성적 아님 · 루프가 어디까지 왔나)\n")
P("| 판 | 공격 통과 | 정상 멈춤 (차단) |")
P("|---|---|---|")
for v in ("v3b",) + tuple(FIX):
    a, na, s, nn, b = tot(rows, v)
    P(f"| {v} | {pct(a, na)} | {pct(s, nn)} ({b}) |")
P(f"| 비교군 | {pct(sum(r['gen'][0] or 0 for r in rows), na_all)} | {pct(sum(r['gen'][1] or 0 for r in rows if r['n'][1]), nn_all)} |")
P("")
P("## 5. 같이 말해야 하는 한계\n")
P("- 「안 본 자료」 0은 그 묶음 범위의 0이다 — 「인젝션 완전 차단」이 아니다. 공개 묶음 상당수는 공격만 있어 정상 대가를 못 잰다(3절 「정상 대조 없음」).")
P("- 적대적·적응형·짝 묶음은 같은 팀이 판을 읽고 쓴 화이트박스다. 적응형은 그 판을 피하려고 썼으니 그 판에 불리하고, 다음 판은 그 결과를 보고 만들었으니 다음 판에는 본 자료다.")
P("- 막을수록 정상 멈춤(사람 확인)이 는다 — 대가는 2·3절의 정상 멈춤 칸이다. 정상 차단은 거의 0이고 멈춤은 사람 확인이다.")
P("- v4～v14는 v2 측정 기록에서 계산한 후보다. 공개 데모 서버에 올린 판은 v3 그대로다.")
print("\n".join(out))
