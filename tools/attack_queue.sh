#!/bin/bash
# 측정 대기열 — 서버가 비면(측정 프로세스 없음 · hold 없음) 다음 묶음을 띄운다. 08:25 넘으면 새로 안 띄운다(11-20 hackathon-cc).
# 배경으로 하나만 띄운다(둘을 띄우면 같은 빈 틈에 둘 다 run을 시도한다). 띄운 줄만 찍는다 — 끝 알림은 따로 DONE 폴링.
# 사용: queue.sh <파일:이름> ...    (파일 = attack/ 아래 .json 없이 · 이름 = attack- 뒤)
cd /home/turtle/projects/02-hackathon/2026-TRILLION-AGENT-AI-HACKATHON/hackathon/2026-11-19-본선/moonjigi-wt-attack
HOLD=$HOME/.local/state/moonjigi-bench/hold
STOP_AT=$(date -d '2026-11-20 08:25' +%s)
for item in "$@"; do
  F=${item%%:*}; N=${item##*:}
  while :; do
    [ "$(date +%s)" -ge "$STOP_AT" ] && { echo "[$(date +%T)] 08:25 넘음 — $N 부터 안 띄움"; exit 0; }
    # status 는 pgrep이 비어도 IDLE을 안 찍는다(파이프 끝 sed의 종료 코드) — 서버에서 직접 pgrep
    if [ ! -e "$HOLD" ] && ! ssh -o BatchMode=yes -o ConnectTimeout=10 -o UserKnownHostsFile=$HOME/.local/state/ncp-inference/known_hosts root@$(cat $HOME/.local/state/ncp-inference/ip) "pgrep -f 'scenarios attack/[a]ttack-' >/dev/null"; then break; fi
    sleep 20
  done
  echo "[$(date +%T)] 띄움 $N"
  tools/bench_naver.sh run attack/$F.json attack-$N 3 --pii --gen 2>&1 | tail -n 2
  sleep 30
done
echo "[$(date +%T)] QUEUE_EMPTY"
