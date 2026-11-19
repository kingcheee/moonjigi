# 무대 통 검사 (Playwright)

`00-본선-준비.md` 「통 검사」 절의 순서를 그대로 도는 스크립트다. 리허설 전에 한 번 돌려 기계 시간과 콘솔 에러를 본다.

```
export NODE_PATH=~/workspace/03-agents/naver-agent/node_modules
mkdir -p /tmp/stage-out
# 무대 통 검사: 탭 A(라이브 ①) → B(B1 재생) → C(A2 재생) → D(규칙 끈 판 재생 → 규칙 켬 → 라이브 ④b → N)
node tools/stagecheck/stage.js http://127.0.0.1:8899 /tmp/stage-out 064520-refund-reply-32e5
# 라이브 한 판(규칙 켬 → refund-reply → 사람 확인 → N) + 429 확인
node tools/stagecheck/shot_live.js http://127.0.0.1:8899 /tmp/stage-out
# ?hold=1 재생 대기
node tools/stagecheck/shot_hold.js http://127.0.0.1:8899 /tmp/stage-out
# 재생 판 여러 개를 끝까지 돌려 화면을 찍는다
node tools/stagecheck/shot_replay.js http://127.0.0.1:8899 /tmp/stage-out replay-B1-delete-spree replay-A2-wipe
```

- 첫 인자는 게이트 주소다(Brev 터널 `http://127.0.0.1:8899` · 노트북 예비 서버 `http://127.0.0.1:8896` · 네이버 공개 서버 `http://211.233.192.32:8899`)
- `stage.js`와 `shot_live.js`는 라이브 판을 실제로 돌린다(판정 서버를 쓴다). 측정(`unseen_all.sh`)이 도는 동안에는 돌리지 않는다
- 기준값(11-19 15:47): ① 2.1·2.1·4.7초 · ② 15.4초 · ③ 1.3초 · ④a 8.4초 · ④b 5.4초 + 0.8초 → 기계 시간 합계 40.3초 · 콘솔 에러 0
