#!/usr/bin/env bash
# 문지기 공개 데모 배포 — 노트북 → 네이버클라우드 L40S.
#
# 서버 안에서 게이트 서버(server.py)를 0.0.0.0:8899 로 띄운다. 판정 서버(Zoro-1 serve.py --mode decide, :30001)는
# 이미 떠 있다고 보고 건드리지 않는다. **밖으로 여는 포트는 8899 하나뿐이다 — 30001은 인증 없는 채팅 엔드포인트라 절대 열지 않는다.**
#
#   deploy/naver.sh            # 코드·화면·기록을 올리고 게이트 서버를 (다시) 띄운다. 여러 번 돌려도 된다 — 최신으로 덮인다
#   deploy/naver.sh status     # 서버 안 · 노트북 → 공인 IP 두 군데에서 /health, 30001 이 밖에서 닫혀 있는지
#   deploy/naver.sh acg        # 방화벽(ACG)에 8899 인바운드 한 줄 추가(없을 때만)
#   deploy/naver.sh acg-remove # 그 한 줄 삭제
#   deploy/naver.sh protect    # (선택) 서버 iptables 로 8899 의 IP당 동시 접속·새 접속 속도 제한
#   deploy/naver.sh unprotect
#   deploy/naver.sh stop       # 게이트 서버만 내린다(판정 서버·서버 자체는 그대로)
#   deploy/naver.sh logs       # 게이트 서버 출력 꼬리
#
# 환경변수:
#   IP     서버 공인 IP (기본: ~/.local/state/ncp-inference/ip — server-work 의 up.sh 가 적는다)
#   CORE   gate.py·server.py·worker.py·scenes.json·web/·runs-live/ 를 가져올 폴더 (기본: 이 워크트리)
#          main 작업 트리의 최신 코드로 올리려면  CORE=../moonjigi deploy/naver.sh
#   EXTRA  CORE 에 없는 web/·runs-live/ 파일을 더 얹을 폴더 (기본: 이 워크트리 — index.html·try.html·pi-*.jsonl). 겹치면 CORE 가 이긴다
#   PORT   공개 포트 (기본 8899)
#   POLICY 게이트 서버 기본 정책 판 (기본 v3)
#
# 서버·방화벽 변경은 ~/workspace/01-infra/server-work/docs/setup-ledger.md 에 적는다. 서버 반납은 server-work 의 bin/down.sh.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WT="$(cd "$HERE/.." && pwd)"
STATE="$HOME/.local/state/ncp-inference"
SW="$HOME/workspace/01-infra/server-work/naver"
IP="${IP:-$(cat "$STATE/ip" 2>/dev/null || true)}"
CORE="$(cd "${CORE:-$WT}" && pwd)"
EXTRA="$(cd "${EXTRA:-$WT}" && pwd)"
PORT="${PORT:-8899}"
POLICY="${POLICY:-v3}"   # 게이트 서버 기본 정책 판(요청마다 "policy"로 바꿀 수 있다)
REMOTE=/root/moonjigi-demo
UNIT=moonjigi-gate
ACG=397049
VPC=148474
ACG_DESC="moonjigi-demo-$PORT"
SSH_OPTS=(-o BatchMode=yes -o StrictHostKeyChecking=accept-new -o "UserKnownHostsFile=$STATE/known_hosts" -o ConnectTimeout=10)

[ -n "$IP" ] || { echo "ERROR: 서버 IP 를 모른다 — IP=… 로 주거나 server-work 의 up.sh 로 서버를 띄운다" >&2; exit 1; }
log() { echo "[$(date +%H:%M:%S)] $*"; }
srv() { ssh "${SSH_OPTS[@]}" "root@$IP" "$@"; }
ncp() { ( set -a; . "$HOME/.config/server-work/naver.env"; set +a; python3 "$SW/bin/ncp-api.py" "$@" ); }

acg_has() {
  ncp getAccessControlGroupRuleList accessControlGroupNo=$ACG accessControlGroupRuleTypeCode=INBND |
    python3 -c 'import json,sys; rs=json.load(sys.stdin)["getAccessControlGroupRuleListResponse"]["accessControlGroupRuleList"]; sys.exit(0 if any(r.get("portRange")==sys.argv[1] and r.get("ipBlock")=="0.0.0.0/0" for r in rs) else 1)' "$PORT"
}
acg_rule=(vpcNo=$VPC accessControlGroupNo=$ACG accessControlGroupRuleList.1.protocolTypeCode=TCP
          accessControlGroupRuleList.1.ipBlock=0.0.0.0/0 "accessControlGroupRuleList.1.portRange=$PORT")

push() (   # 서브셸 — 임시 폴더 정리 trap 이 밖으로 새지 않게
  for f in gate.py server.py worker.py scenes.json; do [ -f "$CORE/$f" ] || { echo "ERROR: $CORE/$f 없음" >&2; exit 1; }; done
  stage="$(mktemp -d)"; trap 'rm -rf "$stage"' EXIT
  # 1) CORE: 코드 + 화면 + 기록   2) EXTRA: CORE 에 없는 화면·기록만 얹는다(--ignore-existing → 겹치면 CORE 가 이긴다)
  rsync -a --exclude '__pycache__' "$CORE/gate.py" "$CORE/server.py" "$CORE/worker.py" "$CORE/scenes.json" "$stage/"
  for d in web runs-live; do
    mkdir -p "$stage/$d"
    [ -d "$CORE/$d" ] && rsync -a --exclude '__pycache__' "$CORE/$d/" "$stage/$d/"
    [ "$EXTRA" != "$CORE" ] && [ -d "$EXTRA/$d" ] && rsync -a --ignore-existing --exclude '__pycache__' "$EXTRA/$d/" "$stage/$d/"
  done
  # 화면이 web/scenes.json(장면의 메일함·파일·일정)을 읽으면 CORE 의 scenes.json 으로 맞춘다 — server.py 는 web/ 밖 파일을 내주지 않는다
  [ -f "$stage/web/scenes.json" ] && cp "$CORE/scenes.json" "$stage/web/scenes.json"
  log "올린다: CORE=$CORE EXTRA=$EXTRA → root@$IP:$REMOTE  (web: $(ls "$stage/web" | tr '\n' ' '))"
  srv "mkdir -p $REMOTE/logs"
  # --delete 를 쓰지 않는다 — 서버에서 새로 생긴 판(runs-live)·검문 기록(logs)을 지우지 않게
  rsync -a -e "ssh ${SSH_OPTS[*]}" "$stage/" "root@$IP:$REMOTE/"
)

start() {
  srv "cat > /etc/systemd/system/$UNIT.service" <<UNIT_EOF
[Unit]
Description=moonjigi gate server (public demo :$PORT -> Zoro-1 judge 127.0.0.1:30001)
After=network-online.target

[Service]
WorkingDirectory=$REMOTE
ExecStart=/usr/bin/python3 $REMOTE/server.py --upstream http://127.0.0.1:30001 --host 0.0.0.0 --port $PORT --policy $POLICY
Restart=always
RestartSec=2
StandardOutput=append:$REMOTE/logs/server.out
StandardError=append:$REMOTE/logs/server.out

[Install]
WantedBy=multi-user.target
UNIT_EOF
  srv "systemctl daemon-reload && systemctl enable -q $UNIT && systemctl restart $UNIT && sleep 2 && systemctl is-active $UNIT && curl -s -m 5 127.0.0.1:$PORT/health | head -c 300; echo"
}

status() {
  echo "── 서버 안"
  srv "systemctl is-active $UNIT; curl -s -m 5 -o /dev/null -w 'health %{http_code}\n' 127.0.0.1:$PORT/health; curl -s -m 5 -o /dev/null -w 'judge(30001, 서버 안) %{http_code}\n' 127.0.0.1:30001/v1/models" || true
  echo "── 노트북 → 공인 IP"
  curl -s -m 6 -o /dev/null -w "http://$IP:$PORT/health %{http_code}\n" "http://$IP:$PORT/health" || echo "http://$IP:$PORT/health 닿지 않음"
  curl -s -m 6 -o /dev/null -w "http://$IP:30001/v1/models %{http_code}  ← 200 이면 안 된다\n" "http://$IP:30001/v1/models" || echo "http://$IP:30001 닿지 않음 (정상 — 닫혀 있다)"
  echo "── 다른 네트워크에서도 본다:  curl -s -m 6 http://$IP:$PORT/health   (휴대폰 데이터 · 다른 서버)"
}

case "${1:-deploy}" in
  deploy)  push; start; log "끝. 공개하려면: deploy/naver.sh acg  → http://$IP:$PORT/" ;;
  status)  status ;;
  acg)     if acg_has; then log "ACG $ACG 에 TCP $PORT 0.0.0.0/0 이미 있음"; else
             ncp addAccessControlGroupInboundRule "${acg_rule[@]}" "accessControlGroupRuleList.1.accessControlGroupRuleDescription=$ACG_DESC" >/dev/null && log "ACG $ACG 에 인바운드 TCP $PORT 0.0.0.0/0 추가($ACG_DESC)"; fi ;;
  acg-remove) ncp removeAccessControlGroupInboundRule "${acg_rule[@]}" >/dev/null && log "ACG $ACG 에서 TCP $PORT 0.0.0.0/0 삭제" ;;
  protect) # IP 하나가 동시에 20개 넘게 붙거나 새 접속을 분당 240개 넘게 열면 거절. 서버를 반납하면 같이 사라진다
           srv "iptables -C INPUT -p tcp --dport $PORT -m connlimit --connlimit-above 20 --connlimit-mask 32 -j REJECT --reject-with tcp-reset 2>/dev/null || iptables -I INPUT -p tcp --dport $PORT -m connlimit --connlimit-above 20 --connlimit-mask 32 -j REJECT --reject-with tcp-reset
                iptables -C INPUT -p tcp --dport $PORT --syn -m hashlimit --hashlimit-name mjg --hashlimit-mode srcip --hashlimit-above 240/min --hashlimit-burst 120 -j DROP 2>/dev/null || iptables -I INPUT -p tcp --dport $PORT --syn -m hashlimit --hashlimit-name mjg --hashlimit-mode srcip --hashlimit-above 240/min --hashlimit-burst 120 -j DROP
                iptables -S INPUT | grep -- '--dport $PORT'" ;;
  unprotect) srv "iptables -D INPUT -p tcp --dport $PORT -m connlimit --connlimit-above 20 --connlimit-mask 32 -j REJECT --reject-with tcp-reset 2>/dev/null; iptables -D INPUT -p tcp --dport $PORT --syn -m hashlimit --hashlimit-name mjg --hashlimit-mode srcip --hashlimit-above 240/min --hashlimit-burst 120 -j DROP 2>/dev/null; iptables -S INPUT | grep -c -- '--dport $PORT' || true" ;;
  stop)    srv "systemctl disable -q --now $UNIT; systemctl is-active $UNIT || true" ;;
  logs)    srv "tail -n ${2:-40} $REMOTE/logs/server.out" ;;
  *)       sed -n '2,24p' "$0"; exit 1 ;;
esac
