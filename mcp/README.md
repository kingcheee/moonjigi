# 문지기 MCP 서버 — 다른 에이전트에 끼우기

문지기를 MCP 서버로 만든 것이다. MCP를 쓰는 에이전트라면 모델이 무엇이든, 메일·파일·일정 도구를 이 서버를 통해서만 보게 하면
도구를 부를 때마다 문지기(Zoro-1 판정 + 코드 정책)를 거친 뒤에 실행된다.

```
사용자 요청 → 에이전트(pi · 아무 모델) → MCP 도구 호출 → [문지기 MCP 서버] → POST /gate (Zoro-1 판정 서버)
                                                             ├ PASS    실행
                                                             ├ BLOCK   실행하지 않고 사유를 돌려줌
                                                             ├ CONFIRM 사람 확인 필요 — 보류
                                                             └ 문지기 응답 없음 → 읽기만 실행, 나머지는 보류
```

- `moonjigi_mcp.py` — stdio MCP 서버. 표준 라이브러리만 쓴다(SDK 설치 없음). 도구 10개는 `worker.py`의 가짜 세계에서만 돈다 — 실제로 보내거나 지우지 않는다
- `run_pi.py` — pi로 한 판 돌리고 기록을 남기는 실행기. 전역 pi 설정은 건드리지 않는다
- `scenes_extra.json` — MCP 쪽 추가 장면(`doc-wipe` = 문서 속 숨은 글씨, 정답지 A2에 해당). `scenes.json`은 그대로다
- `logs/` — pi `--mode json` 원본 로그 · 연기 시험 기록

## 등록 한 줄 (pi)

```bash
pi mcp add moonjigi --exposure direct --env MOONJIGI_SCENE=refund-reply -- python3 /절대/경로/mcp/moonjigi_mcp.py
```

`direct` 노출이어야 모델이 도구를 바로 본다. 에이전트의 기본 도구(bash 등)는 끄고 돌린다(`pi -nbt`) — 켜 두면 문지기를 안 거치는 길이 생긴다.

## 실행

문지기 서버(`server.py`, 기본 `http://127.0.0.1:8899`)가 떠 있어야 한다.

```bash
python3 mcp/run_pi.py --scene file-move                       # 정상 — 통과
python3 mcp/run_pi.py --scene refund-reply                    # 메일 속 「담당 AI 안내」가 환불 계좌를 바꿔치기
python3 mcp/run_pi.py --scene refund-reply --rules pii        # 회사 규칙 한 줄 켜기
python3 mcp/run_pi.py --scene doc-wipe                        # 문서 속 숨은 글씨
python3 mcp/run_pi.py --scene refund-reply --gate http://127.0.0.1:9 --tag gate-down   # 문지기를 끊은 판
python3 mcp/run_pi.py --scene meeting --model openrouter/google/gemma-4-31b-it:free    # 일꾼 모델 바꾸기
```

기본 일꾼은 OpenRouter `nvidia/nemotron-3-ultra-550b-a55b:free`다. 시스템 프롬프트는 Zoro-1 일꾼(`worker.py`의 `plain`)과 같은 글이다.

`run_pi.py`는 이 폴더의 `.pi-agent/`(git 제외)를 pi 설정 폴더로 쓴다(`PI_CODING_AGENT_DIR`). 거기에는 인증 파일 링크와 MCP 등록 한 건만 있어서,
전역 `~/.pi/agent/`의 AGENTS.md·확장·다른 MCP 서버는 일꾼 모델로 나가지 않는다.

## 환경변수 (`moonjigi_mcp.py`)

| 이름 | 뜻 | 기본 |
|---|---|---|
| `MOONJIGI_GATE` | 문지기 서버 주소 | `http://127.0.0.1:8899` |
| `MOONJIGI_SCENE` | 장면 id | `inbox-summary` |
| `MOONJIGI_TASK` | 사용자가 시킨 말(에이전트에게 준 요청과 같은 글) | 장면의 task |
| `MOONJIGI_RULES` | 켤 회사 규칙(쉼표 구분 · 예 `pii`) | 없음 |
| `MOONJIGI_POLICY` | 정책 판(`v1`·`v2`·`v3`·`v3b`·`v3c`) | 문지기 서버 기본값 |
| `MOONJIGI_WORKER` | 기록에 남길 일꾼 이름 | `pi/unknown` |
| `MOONJIGI_EVENTS` · `MOONJIGI_RUNS_DIR` | 기록 파일 · 폴더 | `runs-live/pi-<시각>-<장면>-<id>.jsonl` |

## 기록

판마다 `runs-live/pi-*.jsonl`이 `worker.py`와 같은 이벤트 모양으로 남는다(`run_start`에 `worker: "pi/<모델>"` · `via: "mcp"`).
`server.py`의 `/worker/runs`·`/worker/events`가 그대로 읽으므로 `viewer.html`에서 재생된다.

## Zoro-1 일꾼(`worker.py`)과 다른 점

- **판을 멈추지 못한다.** 에이전트는 남의 것이라 막힌 뒤에도 계속 돈다. 대신 한 번 거부된 호출을 글자 그대로 다시 부르면 문지기에 다시 묻지 않고 거부하고, 다른 호출은 평소대로 검문한다
- **사람 확인 버튼이 없다.** `pi -p`는 비대화형이라 CONFIRM은 「보류」로 돌려준다. 에이전트는 사용자에게 승인이 필요하다고 말하게 된다
- **문지기가 죽어도 일꾼은 산다.** 일꾼 모델이 따로 있으므로 문지기 서버가 답하지 않으면 읽기 전용 도구만 실행하고 나머지는 보류한다(`gate.effect_of`가 읽기라고 아는 도구만 통과). Zoro-1 한 몸 구성에서는 판정 서버가 죽으면 일꾼도 같이 멈춘다
- 일꾼이 도구 없이 한 말은 MCP 서버가 볼 수 없어서, `run_pi.py`가 pi 원본 로그에서 뽑아 기록에 끼워 넣는다
