#!/bin/bash
# 박규연 새(보지 않은) 시나리오 측정 — Brev 안에서 한 번에 돈다. 정책·문턱은 고치지 않는다(측정 전용).
#   사용: bash unseen_all.sh 새-시나리오.json            (기본: 반복 3 · 접두어 unseen)
#         REPEAT=1 PREFIX=dryrun bash unseen_all.sh ../사전실측/scenarios.json   (드라이런)
#         WITH_V3C=1 …                                      (v3c를 실제로도 한 번 돈다 — 기본은 v2 기록에서 계산)
# 순서: v2를 맨 먼저(처음 보는 호출 = rep 0 지연이 깨끗하다) → v3·v3b·v3c는 v2 기록에서 계산 → v1 → v2+규칙(pii) → 비교군(생성형 판정)
set -u
cd "$(dirname "$0")" && mkdir -p runs
SRC=${1:?시나리오 파일}
REPEAT=${REPEAT:-3}
PREFIX=${PREFIX:-unseen}
URL=${URL:-http://127.0.0.1:30001}
SC="$PREFIX-scenarios.json"
t0=$(date +%s)
stamp(){ echo "[$(date +%H:%M:%S) +$(( $(date +%s) - t0 ))s] $*"; }

# 양식 예시 3건(N101·A101·H101 — 우리가 쓰고 돌려 본 것)은 빼고, 모양을 검사한다
python3 - "$SRC" "$SC" <<'EOF' || exit 1
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
assert isinstance(d, list), "시나리오 파일은 목록이어야 한다"
keep = [x for x in d if x.get("id") not in ("N101", "A101", "H101")]
ids = [x.get("id") for x in keep]
bad = []
if len(set(ids)) != len(ids): bad.append("id 중복: " + ", ".join(sorted({i for i in ids if ids.count(i) > 1})))
for x in keep:
    for k in ("id", "expect", "user_request", "tool_call"):
        if not x.get(k): bad.append(f"{x.get('id')}: {k} 없음")
    if x.get("expect") not in ("PASS", "CONFIRM", "BLOCK"): bad.append(f"{x.get('id')}: expect={x.get('expect')}")
    tc = x.get("tool_call") or {}
    if not isinstance(tc, dict) or not tc.get("name"): bad.append(f"{x.get('id')}: tool_call.name 없음")
if bad:
    print("시나리오 모양 오류:\n  " + "\n  ".join(bad)); sys.exit(1)
json.dump(keep, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
kinds = {}
for x in keep:
    k = x.get("kind") or {"N": "normal", "A": "attack", "H": "ambiguous"}.get(x["id"][:1].upper(), "other")
    kinds[k] = kinds.get(k, 0) + 1
print(f"시나리오 {len(d)}건 → {len(keep)}건(예시 {len(d) - len(keep)}건 뺌) · 종류 {kinds}")
EOF

stamp "v2 × $REPEAT"
python3 eval.py --url "$URL" --scenarios "$SC" --out "runs/$PREFIX-v2-r$REPEAT" --repeat "$REPEAT" --policy v2 > "runs/$PREFIX-v2-r$REPEAT.log" 2>&1 || stamp "v2 실패"
stamp "v3·v3b·v3c ← v2 기록"
python3 variants_from_v2.py "runs/$PREFIX-v2-r$REPEAT" --out "runs/$PREFIX-v3x-from-v2" > /dev/null || stamp "계산 실패"
stamp "v1 × $REPEAT"
python3 eval.py --url "$URL" --scenarios "$SC" --out "runs/$PREFIX-v1-r$REPEAT" --repeat "$REPEAT" --policy v1 > "runs/$PREFIX-v1-r$REPEAT.log" 2>&1 || stamp "v1 실패"
stamp "v2 + 규칙 pii × 1"
python3 eval.py --url "$URL" --scenarios "$SC" --out "runs/$PREFIX-v2-pii-r1" --repeat 1 --policy v2 --rules pii > "runs/$PREFIX-v2-pii-r1.log" 2>&1 || stamp "pii 실패"
stamp "비교군(생성형 판정)"
python3 ../사전실측/moonjigi_eval.py --url "$URL" --scenarios "$SC" --lang en --gen-baseline --out "runs/$PREFIX-gen" > "runs/$PREFIX-gen.log" 2>&1 || stamp "비교군 실패"
if [ "${WITH_V3C:-0}" = 1 ]; then
  stamp "v3c × 1(실제)"
  python3 eval.py --url "$URL" --scenarios "$SC" --out "runs/$PREFIX-v3c-r1" --repeat 1 --policy v3c > "runs/$PREFIX-v3c-r1.log" 2>&1 || stamp "v3c 실패"
fi
stamp "DONE"
