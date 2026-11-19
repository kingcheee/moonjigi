#!/bin/bash
# tools/attack_after_run.sh <attack/ 아래 파일 이름(.json 없이)> <이름(attack- 뒤)> — fetch → 시나리오 사본 → unseen_report → v4 표(variants_v4). v5·v6·v7은 따로: variants_v5.py · variants_v7.py(v6 포함)
set -e
cd /home/turtle/projects/02-hackathon/2026-TRILLION-AGENT-AI-HACKATHON/hackathon/2026-11-19-본선/moonjigi-wt-attack
F=$1; N=$2
tools/bench_naver.sh fetch >/dev/null
cp attack/$F.json attack-$N-scenarios.json
python3 unseen_report.py --prefix attack-$N --root . --out runs/attack-$N-report.md >/dev/null
python3 variants_v4.py runs/attack-$N-v2-r3 > runs/attack-$N-v4.md
cat runs/attack-$N-report.md | head -40
echo; cat runs/attack-$N-v4.md
