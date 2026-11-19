#!/usr/bin/env python3
"""공개 데모 서버가 실제로 도는지 밖에서 확인한다 — 올린 직후와 제출 전에 한 번씩.

  python3 deploy/check_public.py                        # 기본 http://211.233.192.32:8899
  python3 deploy/check_public.py http://127.0.0.1:8897  # 미리보기 서버
  python3 deploy/check_public.py --no-live              # 라이브 판은 돌리지 않는다(판정 서버를 쓰지 않는다)

보는 것: 화면 파일 200 · /health 의 정책 해시가 이 작업 트리의 gate.py 와 같은지 · 저장된 판 재생(27통 삭제 판) ·
라이브 한 판(계좌 답장 + 회사 규칙 → 사람 확인 → 거절 → 보낸 메일 0통). 라이브 판은 판정 서버를 한 번 쓴다.
표준 라이브러리만 쓴다. 하나라도 틀리면 종료 코드 1.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import gate  # noqa: E402

BASE = next((a for a in sys.argv[1:] if a.startswith("http")), "http://211.233.192.32:8899").rstrip("/")
LIVE = "--no-live" not in sys.argv
PAGES = ["/", "/try.html", "/viewer.html"] + [a for a in sys.argv[1:] if a.startswith("/")]
FAILS: list[str] = []


def http(path: str, body: dict | None = None, timeout: float = 15):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, headers={"Content-Type": "application/json"} if data else {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:  # noqa: BLE001 — 연결 실패도 결과로 적는다
        return 0, repr(e).encode()


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("OK  " if ok else "FAIL") + f" {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        FAILS.append(name)


def events(run: str) -> dict:
    code, raw = http(f"/worker/events?run={run}&since=0")
    return json.loads(raw) if code == 200 else {"events": [], "error": code}


def main() -> int:
    print(f"대상 {BASE}")
    for page in PAGES:
        code, raw = http(page)
        check(f"GET {page}", code == 200 and len(raw) > 200, f"{code} · {len(raw)}바이트")

    code, raw = http("/health")
    h = json.loads(raw) if code == 200 else {}
    check("/health ok", bool(h.get("ok")), f"policy {h.get('policy')} · upstream {'응답' if h.get('models') else '없음'}")
    check("정책 해시가 이 작업 트리와 같다", h.get("policy_versions") == gate.POLICY_VERSIONS and h.get("rules_version") == gate.RULES_VERSION,
          f"서버 {h.get('policy_versions')} {h.get('rules_version')}")

    code, raw = http("/web-scenes-probe-does-not-exist")
    check("없는 경로는 404", code == 404, str(code))

    ev = events("replay-B1-delete-spree").get("events", [])
    blocks = sum(1 for e in ev if e.get("type") == "verdict" and e.get("final") and e["verdict"].get("decision") == "BLOCK")
    check("재생: 27통 삭제 판", blocks == 27, f"차단 {blocks}건 · 이벤트 {len(ev)}개")

    if not LIVE:
        print("라이브 판은 건너뜀(--no-live)")
        return 1 if FAILS else 0

    code, raw = http("/worker/run", {"scene": "refund-reply", "rules": ["pii"]})
    if code == 429:
        check("라이브: 판 시작", False, "429 — 다른 라이브 판이 2개 돌고 있다. 잠시 뒤 다시")
        return 1
    run = json.loads(raw).get("run_id") if code == 200 else None
    check("라이브: 판 시작", bool(run), f"{code} · run {run}")
    if not run:
        return 1
    t0, confirmed, d = time.time(), False, {}
    while time.time() - t0 < 120:
        d = events(run)
        ev = d.get("events", [])
        waiting = [e for e in ev if e.get("type") == "confirm_wait"]
        if waiting and not confirmed:
            v = next((e["verdict"] for e in ev if e.get("type") == "verdict" and e.get("final") and e.get("call_id") == waiting[-1]["call_id"]), {})
            check("라이브: 회사 규칙으로 사람 확인", v.get("decision") == "CONFIRM" and str(v.get("rule", "")).startswith("company rule"),
                  f"{v.get('decision')} · {v.get('rule')} · {time.time() - t0:.1f}초 만에")
            code, _ = http("/worker/confirm", {"run": run, "approve": False})
            check("라이브: 거절 보내기", code == 200, str(code))
            confirmed = True
        if d.get("done"):
            break
        time.sleep(0.5)
    end = next((e for e in d.get("events", []) if e.get("type") == "run_end"), None)
    check("라이브: 판이 끝났다", end is not None, f"{(end or {}).get('reason')} · {(end or {}).get('wall_s')}초")
    check("라이브: 보낸 메일 0통", end is not None and end.get("outbox") == [], f"outbox {len((end or {}).get('outbox', []))}")
    check("라이브: 사람 확인을 거쳤다", confirmed)
    return 1 if FAILS else 0


if __name__ == "__main__":
    rc = main()
    print("결과: " + ("전부 통과" if rc == 0 else f"실패 {len(FAILS)}건 — {', '.join(FAILS)}"))
    sys.exit(rc)
