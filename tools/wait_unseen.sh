#!/bin/bash
# 박규연 새 시나리오가 오는지 지켜본다. 오면(또는 마감·서버 이상이면) 한 줄 찍고 끝난다.
# 측정은 띄우지 않는다 — 올리다 만 파일일 수 있어, 띄우는 것은 파일을 확인한 뒤에 한다.
#   bash tools/wait_unseen.sh                      (기본: 마감 2026-11-20 04:00 · 3분 간격)
#   DEADLINE="2026-11-20 05:00" EVERY=120 bash tools/wait_unseen.sh
# 보는 곳: ① 노트북 moonjigi/ 와 ~/Downloads 에 새로 생긴 .json  ② Brev ~/moonjigi-run/moonjigi/ 에 새로 생긴 .json
# 끝나는 말: ARRIVED local <경로> · ARRIVED brev <이름> · DEADLINE … · SERVER_PROBLEM …(게이트·판정 서버·ssh가 3번 잇달아 이상)
DEADLINE=${DEADLINE:-2026-11-20 04:00}
EVERY=${EVERY:-180}
HOST=${HOST:-moonjigi-zoro1}
HERE=$(cd "$(dirname "$0")/.." && pwd)
start=$(date +%s)
end=$(date -d "$DEADLINE" +%s) || exit 9
probe() {
  timeout 25 ssh -o BatchMode=yes "$HOST" 'cd ~/moonjigi-run/moonjigi 2>/dev/null && ls *.json 2>/dev/null | tr "\n" "|"; echo; echo "gate=$(curl -s -m 5 -o /dev/null -w "%{http_code}" 127.0.0.1:8899/health) judge=$(curl -s -m 5 -o /dev/null -w "%{http_code}" 127.0.0.1:30001/v1/models)"' 2>/dev/null
}
base=""
bad=0
while :; do
  f=$(find "$HERE" ~/Downloads -maxdepth 1 -type f -name '*.json' -newermt "@$start" ! -name '*-scenarios.json' 2>/dev/null | head -1)
  if [ -n "$f" ]; then echo "ARRIVED local $f"; exit 0; fi
  r=$(probe)
  list=$(echo "$r" | sed -n 1p)
  stat=$(echo "$r" | sed -n 2p)
  if [ "$stat" = "gate=200 judge=200" ]; then
    bad=0
    if [ -z "$base" ]; then
      base="$list"
    elif [ "$list" != "$base" ]; then
      new=$(echo "$list" | tr '|' '\n' | grep -v -x -F -f <(echo "$base" | tr '|' '\n') | grep -v -e '-scenarios\.json$' | tr '\n' ' ')
      if [ -n "${new// /}" ]; then echo "ARRIVED brev $new"; exit 0; fi
      base="$list"
    fi
  else
    bad=$((bad + 1))
    if [ "$bad" -ge 3 ]; then echo "SERVER_PROBLEM ${stat:-ssh 응답 없음}"; exit 3; fi
  fi
  if [ "$(date +%s)" -ge "$end" ]; then echo "DEADLINE $DEADLINE — 새 시나리오 파일이 안 왔다"; exit 2; fi
  sleep "$EVERY"
done
