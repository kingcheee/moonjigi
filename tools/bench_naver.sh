#!/bin/bash
# 공격 측정 — 네이버 서버에서 「우리가 쓴 공격 · 공개 인젝션 예시」 시나리오를 잰다(unseen 측정과 따로).
#
#   tools/bench_naver.sh run <시나리오.json> <접두어> [반복=1] [--pii]   서버에서 배경으로 띄우고 바로 돌아온다
#   tools/bench_naver.sh status                                         도는 중인지 · 마지막 로그
#   tools/bench_naver.sh fetch                                          서버 runs/attack-* → 이 작업 트리 runs/
#   tools/bench_naver.sh stop                                           도는 측정을 끊는다(영상 녹화 · 무대 전)
#
# 공개 데모(/root/moonjigi-demo · 유닛 moonjigi-gate)는 건드리지 않는다. 측정은 /root/moonjigi-bench 에서
# 판정 서버(127.0.0.1:30001)를 서버 안에서 직접 부른다 — 8899를 안 거치므로 공개 콘솔 「검문 기록」에 안 찍힌다.
# 단 판정 서버는 공개 데모와 같은 것이다 → 영상 녹화·무대 시간에는 ~/.local/state/moonjigi-bench/hold 를 만들어 run을 막고 stop 한다.
# 순서: v2 × 반복(직답·추론 확률 기록) → v3·v3b·v3c는 v2 기록에서 계산(variants_from_v2.py) → (--pii) v2 + 규칙 pii × 1
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE="$HOME/.local/state/ncp-inference"
HOLD="$HOME/.local/state/moonjigi-bench/hold"
IP="${IP:-$(cat "$STATE/ip")}"
R=/root/moonjigi-bench
SSH_OPTS=(-o BatchMode=yes -o StrictHostKeyChecking=accept-new -o "UserKnownHostsFile=$STATE/known_hosts" -o ConnectTimeout=10)
srv() { ssh "${SSH_OPTS[@]}" "root@$IP" "$@"; }
EXPECT="{'v1': '382259fd0b21', 'v2': 'e8c958fb2898', 'v3': '298d016205cd', 'v3b': '060839ee0c12', 'v3c': '44a950c08114'} d9b8d2e8c13c"

case "${1:-}" in
  run)
    SRC=${2:?시나리오 파일}; P=${3:?접두어(attack-…)}; REP=${4:-1}; PII=${5:-}
    [[ "$P" == attack-* ]] || { echo "접두어는 attack- 로 시작한다(unseen 측정과 섞지 않는다)" >&2; exit 2; }
    [ -e "$HOLD" ] && { echo "HOLD: $HOLD 가 있다 — 영상 녹화·무대 시간이라 측정을 띄우지 않는다" >&2; exit 3; }
    python3 "$HERE/tools/attack_check.py" "$SRC"
    srv "pgrep -f '$R/[e]val.py' >/dev/null" && { echo "BUSY: 서버에서 측정이 이미 돈다 — status 로 본다" >&2; exit 4; }
    srv "mkdir -p $R/runs $R/attack"
    rsync -a -e "ssh ${SSH_OPTS[*]}" "$HERE/gate.py" "$HERE/eval.py" "$HERE/variants_from_v2.py" "$HERE/unseen_report.py" "root@$IP:$R/"
    rsync -a -e "ssh ${SSH_OPTS[*]}" "$SRC" "root@$IP:$R/attack/$P-scenarios.json"
    got=$(srv "cd $R && python3 -c \"import gate; print(gate.POLICY_VERSIONS, gate.RULES_VERSION)\"")
    [ "$got" = "$EXPECT" ] || { echo "정책 해시가 다르다: $got" >&2; exit 5; }
    sha=$(sha256sum "$SRC" | cut -c1-16)
    srv "cd $R && cat > runs/$P.meta <<EOF
server=naver-l40s ($IP) judge=127.0.0.1:30001
scenarios=$(basename "$SRC") sha256=$sha repeat=$REP pii=${PII:+yes}
policy=$got
start=\$(date '+%F %T')
EOF
nohup bash -c 'set -u; cd $R
  echo \"[\$(date +%T)] v2 × $REP\"; python3 eval.py --url http://127.0.0.1:30001 --scenarios attack/$P-scenarios.json --out runs/$P-v2-r$REP --repeat $REP --policy v2 || echo \"[\$(date +%T)] v2 실패\"
  echo \"[\$(date +%T)] v3·v3b·v3c ← v2\"; python3 variants_from_v2.py runs/$P-v2-r$REP --out runs/$P-v3x-from-v2 || echo \"[\$(date +%T)] 계산 실패\"
  if [ -n \"$PII\" ]; then echo \"[\$(date +%T)] v2 + pii × 1\"; python3 eval.py --url http://127.0.0.1:30001 --scenarios attack/$P-scenarios.json --out runs/$P-v2-pii-r1 --repeat 1 --policy v2 --rules pii || echo \"[\$(date +%T)] pii 실패\"; fi
  echo \"[\$(date +%T)] DONE\"' > runs/$P.log 2>&1 &
echo started"
    echo "→ $P 띄움(서버 $R/runs/$P.log) · 끝나면 tools/bench_naver.sh fetch"
    ;;
  status)
    srv "pgrep -af '$R/[e]val.py' | sed 's/^/RUNNING /' || echo IDLE; ls -t $R/runs/*.log 2>/dev/null | head -1 | xargs -r tail -n 4"
    ;;
  fetch)
    mkdir -p "$HERE/runs"
    rsync -a -e "ssh ${SSH_OPTS[*]}" "root@$IP:$R/runs/" "$HERE/runs/" --include='attack-*' --include='attack-*/**' --exclude='*'
    ls -d "$HERE"/runs/attack-* 2>/dev/null | sed "s|$HERE/||"
    ;;
  stop)
    srv "pkill -f '$R/[e]val.py' && echo STOPPED || echo 'NOTHING_RUNNING'"
    ;;
  *) sed -n 2,13p "$0"; exit 1 ;;
esac
