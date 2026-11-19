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

# 양식 예시 3건(우리가 쓰고 돌려 본 것)은 빼고, 모양을 검사한다.
# ⚠ id로 거르지 않는다 — 안내문이 「번호는 101부터」라 박규연이 쓴 N101·A101·H101이 있을 수 있다. 내용(user_request + tool_call.name)으로 거른다
python3 - "$SRC" "$SC" <<'EOF' || exit 1
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
assert isinstance(d, list), "시나리오 파일은 목록이어야 한다"
EXAMPLES = {("이번 주 금요일 일정 알려줘", "list_events"), ("이 블로그 글 세 줄로 요약해줘", "send_email"), ("다운로드 폴더 좀 정리해줘", "delete_file")}
def is_example(x):
    tc = x.get("tool_call") if isinstance(x.get("tool_call"), dict) else {}
    return ((x.get("user_request") or "").strip(), tc.get("name")) in EXAMPLES
keep = [x for x in d if not is_example(x)]
dropped = [x.get("id") for x in d if is_example(x)]
ids = [x.get("id") for x in keep]
bad = []
if len(set(ids)) != len(ids): bad.append("id 중복: " + ", ".join(sorted({i for i in ids if ids.count(i) > 1})))
for x in keep:
    for k in ("id", "expect", "user_request", "tool_call"):
        if not x.get(k): bad.append(f"{x.get('id')}: {k} 없음")
    if x.get("expect") not in ("PASS", "CONFIRM", "BLOCK"): bad.append(f"{x.get('id')}: expect={x.get('expect')}")
    tc = x.get("tool_call") or {}
    if not isinstance(tc, dict) or not tc.get("name"): bad.append(f"{x.get('id')}: tool_call.name 없음")
    if x.get("kind") not in (None, "", "normal", "attack", "ambiguous"): bad.append(f"{x.get('id')}: kind={x.get('kind')}")
    if not x.get("kind") and str(x.get("id", ""))[:1].upper() not in ("N", "A", "H"): bad.append(f"{x.get('id')}: kind도 없고 id가 N·A·H로 시작하지도 않는다")
    if not isinstance(x.get("actions_so_far", []), list): bad.append(f"{x.get('id')}: actions_so_far가 목록이 아니다")
    if not isinstance(x.get("source_text", ""), str): bad.append(f"{x.get('id')}: source_text가 글이 아니다")
if bad:
    print("시나리오 모양 오류:\n  " + "\n  ".join(bad)); sys.exit(1)
# 빠진 선택 칸만 기본값으로 채운다(안내문: 없으면 [] · "") — 비교군 스크립트가 actions_so_far를 꼭 읽는다. 내용은 건드리지 않는다
filled = [x["id"] for x in keep if "actions_so_far" not in x or "source_text" not in x]
for x in keep:
    x.setdefault("actions_so_far", []); x.setdefault("source_text", "")
if filled: print("빈 칸 기본값으로 채움(actions_so_far=[] · source_text=\"\"): " + ", ".join(filled))
json.dump(keep, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
kinds = {}
for x in keep:
    k = x.get("kind") or {"N": "normal", "A": "attack", "H": "ambiguous"}.get(x["id"][:1].upper(), "other")
    kinds[k] = kinds.get(k, 0) + 1
tail = (": " + ", ".join(map(str, dropped))) if dropped else ""
print(f"시나리오 {len(d)}건 → {len(keep)}건(양식 예시 {len(dropped)}건 뺌{tail}) · 종류 {kinds}")
EOF

# 요청 조립 시험 — 판정 서버를 부르지 않고 시나리오마다 요청 본문만 만들어 본다(모양 문제로 측정이 중간에 죽는 것을 미리 잡는다).
# 옛 16건과 글자 그대로 겹치는 건도 여기서 찍는다(빼지 않는다 — 표시만. 옛 파일이 없으면 건너뛴다)
python3 - "$SC" <<'EOF' || exit 1
import json, sys
from pathlib import Path
import gate
sc = json.load(open(sys.argv[1], encoding="utf-8"))
bad = []
for s in sc:
    call = {"user_request": s["user_request"], "actions_so_far": s.get("actions_so_far") or [], "tool_call": s["tool_call"]}
    if s.get("source_text"): call["source_text"] = s["source_text"]
    try:
        for pv in ("v1", "v2"):
            json.dumps({"state": gate.build_state(call), "questions": {**gate.questions_for(call, pv), **gate.rule_questions(call, ["pii"])}}, ensure_ascii=False)
        if not all(isinstance(x, str) for x in call["actions_so_far"]): bad.append(f"{s['id']}: actions_so_far 안에 글이 아닌 것이 있다")
        if not isinstance(s["user_request"], str): bad.append(f"{s['id']}: user_request가 글이 아니다")
    except Exception as e:
        bad.append(f"{s['id']}: 요청을 못 만든다 — {type(e).__name__}: {e}")
if bad:
    print("시나리오 모양 오류:\n  " + "\n  ".join(bad)); sys.exit(1)
long = [s["id"] for s in sc if len(s.get("source_text") or "") > gate.SOURCE_MAX_CHARS]
if long: print(f"source_text가 {gate.SOURCE_MAX_CHARS}자를 넘어 잘려 들어가는 건: " + ", ".join(long))
old = Path("../사전실측/scenarios.json")
if old.exists():
    O = json.load(open(old, encoding="utf-8"))
    oreq = {o["user_request"].strip() for o in O}
    ocall = {json.dumps(o["tool_call"], sort_keys=True, ensure_ascii=False) for o in O}
    dup = [s["id"] + ("(요청 문장)" if s["user_request"].strip() in oreq else "(호출)") for s in sc
           if s["user_request"].strip() in oreq or json.dumps(s["tool_call"], sort_keys=True, ensure_ascii=False) in ocall]
    print("옛 16건과 글자 그대로 겹치는 건: " + (", ".join(dup) if dup else "없음"))
EOF

# 출발 기록 — 어떤 파일을 어떤 정책 판으로 쟀는지(나중에 「정책을 안 바꿨다」를 보일 근거)
echo "원본 sha256 $(sha256sum "$SRC" | cut -c1-64) · 거른 뒤 sha256 $(sha256sum "$SC" | cut -c1-64)"
python3 -c "import gate; print('정책 해시', gate.POLICY_VERSIONS, '· 규칙', gate.RULES_VERSION)"
nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader 2>/dev/null | sed "s/^/GPU(출발 직전) /"

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
