#!/usr/bin/env python3
"""공개 자료 묶음 만들기 — AgentDojo(ethz-spylab/agentdojo, MIT) workspace 스위트의 「앞 묶음에 안 쓴」 정상 과업 → attack/public-agentdojo-ws-normals.json

  git clone https://github.com/ethz-spylab/agentdojo.git <폴더> && git -C <폴더> checkout 089ed468cf3ed0322acc66b0211f26d9d90dbf60
  python3 -I tools/build_public_agentdojo_ws_normals.py <폴더> > attack/public-agentdojo-ws-normals.json
  python3 tools/attack_check.py attack/public-agentdojo-ws-normals.json

정상(kind normal, expect PASS)만 만든다. AgentDojo 코드는 실행하지 않는다 — .py는 ast.parse로 읽기만 하고(상수·f-string·문자열 덧셈·
「", ".join(상수 목록)」만 정적으로 푼다) YAML은 yaml.safe_load. 과업 클래스는 가장 새 판을 쓴다(v1 < v1_1_1 < v1_1_2 < v1_2 < v1_2_2).

뺀 것: build_public_agentdojo.py가 이미 쓴 사용자 과업 — 정상 6·15·18·29·34·33·25·13·35·32, 공격 짝 17·28·0·22·16·24·14·1·3·34.
  조합 과업(task_combinator가 두 과업을 이어 붙인 것) 중 구성 과업에 위 번호가 끼어 있는 것(4·19·23·37·38·39)도 뺐다 —
  판정 호출이 앞 묶음과 겹친다. 남은 과업 중 정답 호출(ground_truth)에 상태 변경 호출이 없는 것(읽기만)은 정상 대조가 안 되어 뺐다.

옮긴 것(원문 그대로): 사용자 과업 문장(UserTask.PROMPT — 조합 과업은 AgentDojo task_combinator의 문장 틀
  「Perform the following tasks in the order they are given: 1. … 2. …」을 소스에서 읽어 채움) · 정답 호출의 인자 ·
  일정·파일 본문(주입 자리는 AgentDojo 정상 기본값).
우리가 한 것:
  ① tool_call = 정답 호출의 첫 상태 변경 호출, actions_so_far = 그 앞의 정답 읽기 호출(호출 하나에 한 줄),
     source_text = 그 읽기들이 돌려줄 글을 「[호출]」 머리와 함께 적은 것(1,500자에서 자름 …). build_public_agentdojo_x.py와 같은 방식.
  ② 도구 이름·인자 이름을 build_public_agentdojo.py처럼 문지기 쪽으로 옮김:
       search_emails→list_mail · get_unread_emails→list_mail(unread=True) · get_received_emails→list_mail ·
       search_calendar_events·get_day_calendar_events→list_events(query·date) · search_contacts_by_name·_by_email→search_contacts ·
       search_files·search_files_by_filename→search_files(query) · get_file_by_id→read_doc(path=파일 이름) · list_files→list_files ·
       create_calendar_event→create_event(start_time→start, end_time→end, 「YYYY-MM-DD HH:MM」→「YYYY-MM-DDTHH:MM」) ·
       append_to_file→write_file(append=True) · create_file→write_file(기존 빌더가 create_file 자리에 write_file을 썼다) ·
       share_file→share_link(email→with, permission r→read·rw→edit) · delete_file→delete_file · delete_email→delete_mail ·
       send_email→send_email(recipients→to, attachments→attach) · 파일 id는 파일 이름으로.
     문지기에 같은 도구가 없는 것은 AgentDojo 이름·인자 그대로 둔다: reschedule_calendar_event · add_calendar_event_participants ·
       cancel_calendar_event · get_current_day 등(일정 id는 그대로 — 기존 빌더도 id→이름은 파일만 바꿨다).
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(sys.argv[1]) / "src/agentdojo"
SUITE = "workspace"
DATA = ROOT / "data/suites" / SUITE
COMMIT = "089ed468cf3ed0322acc66b0211f26d9d90dbf60"
URL = f"https://github.com/ethz-spylab/agentdojo/tree/{COMMIT}/src/agentdojo"
LICENSE = "MIT (Copyright (c) 2024 Edoardo Debenedetti, Jie Zhang, Mislav Balunovic, Luca Beurer-Kellner, Marc Fischer, and Florian Tramèr)"
SET_NOTE = "공개 자료 — AgentDojo workspace(MIT) · 앞 묶음에 안 쓴 정상 과업 · 문장 원문 그대로 · 인자 채우기는 우리가 함 · v4·v5가 안 본 자료 · 정상 대조"
VERSIONS = ["v1", "v1_1", "v1_1_1", "v1_1_2", "v1_2", "v1_2_1", "v1_2_2"]
USED_NORMAL = {6, 15, 18, 29, 34, 33, 25, 13, 35, 32}       # build_public_agentdojo.py NORMALS
USED_ATTACK = {17, 28, 0, 22, 16, 24, 14, 1, 3, 34}         # build_public_agentdojo.py ATTACKS의 사용자 과업
USED = USED_NORMAL | USED_ATTACK
STATE = {"send_email", "delete_email", "create_calendar_event", "cancel_calendar_event", "reschedule_calendar_event",
         "add_calendar_event_participants", "append_to_file", "create_file", "delete_file", "share_file"}
READ_PREFIX = ("get_", "search_", "list_", "read_")
SRC_MAX = 1500


# ---------------------------------------------------------------------------
# AgentDojo .py를 실행하지 않고 읽기
# ---------------------------------------------------------------------------
class Unknown(Exception):
    pass


def ev(n: ast.AST, env: dict):
    if isinstance(n, ast.Constant):
        return n.value
    if isinstance(n, ast.JoinedStr):
        out = ""
        for v in n.values:
            if isinstance(v, ast.Constant):
                out += v.value
            elif isinstance(v, ast.FormattedValue) and v.format_spec is None and v.conversion == -1:
                out += str(ev(v.value, env))
            else:
                raise Unknown("f-string 서식")
        return out
    if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Add):
        return ev(n.left, env) + ev(n.right, env)
    if isinstance(n, ast.Name) and n.id in env:
        return env[n.id]
    if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "self" and n.attr in env:
        return env[n.attr]
    if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "join"
            and isinstance(n.func.value, ast.Constant) and isinstance(n.func.value.value, str) and len(n.args) == 1 and not n.keywords):
        items = ev(n.args[0], env)          # 「구분자".join(상수 목록)」만 — 문자열 상수끼리 잇는 것
        if not (isinstance(items, list) and all(isinstance(x, str) for x in items)):
            raise Unknown("join 대상")
        return n.func.value.value.join(items)
    if isinstance(n, ast.Dict) and all(k is not None for k in n.keys):
        return {ev(k, env): ev(v, env) for k, v in zip(n.keys, n.values)}
    if isinstance(n, (ast.List, ast.Tuple)):
        return [ev(e, env) for e in n.elts]
    raise Unknown(type(n).__name__)


def assigns(body: list, env: dict) -> dict:
    got = {}
    for s in body:
        tg = s.targets[0] if isinstance(s, ast.Assign) and len(s.targets) == 1 else s.target if isinstance(s, ast.AnnAssign) else None
        if isinstance(tg, ast.Name) and getattr(s, "value", None) is not None:
            try:
                env[tg.id] = got[tg.id] = ev(s.value, env)
            except Unknown:
                pass
    return got


def parse_class(c: ast.ClassDef, mod: dict, ver: str, path: str) -> dict:
    env = dict(mod)
    consts = assigns(c.body, env)
    gt = next(s for s in c.body if isinstance(s, ast.FunctionDef) and s.name == "ground_truth")
    stores = [x.id for x in ast.walk(gt) if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Store)]
    local = dict(env)
    for k, v in assigns(gt.body, {**env}).items():
        if stores.count(k) == 1:          # 한 번만 대입되는 지역 변수만 푼다
            local[k] = v
    calls = []
    nodes = [x for x in ast.walk(gt) if isinstance(x, ast.Call) and getattr(x.func, "id", None) == "FunctionCall"]
    for x in sorted(nodes, key=lambda x: (x.lineno, x.col_offset)):
        kw = {k.arg: k.value for k in x.keywords}
        args, missing = {}, []
        for k, v in zip(kw["args"].keys, kw["args"].values):
            try:
                args[ev(k, local)] = ev(v, local)
            except Unknown:
                missing.append(ev(k, local))
                args[ev(k, local)] = None
        calls.append({"fn": ev(kw["function"], local), "args": args, "missing": missing})
    if not isinstance(consts.get("PROMPT"), str):
        raise SystemExit(f"{c.name}: PROMPT를 정적으로 못 읽음")
    return {"ver": ver, "text": consts["PROMPT"], "calls": calls, "url": f"{URL}/{path}", "parts": None}


def combinator_prompt() -> ast.JoinedStr:
    """task_combinator가 조합 과업 문장을 만드는 f-string(PROMPT = f"Perform … 1. {user_task_1.PROMPT} 2. {user_task_2.PROMPT}")."""
    t = ast.parse((ROOT / "task_suite/task_combinators.py").read_text(encoding="utf-8"))
    return next(s.value for s in ast.walk(t) if isinstance(s, ast.Assign) and isinstance(s.targets[0], ast.Name)
                and s.targets[0].id == "PROMPT" and isinstance(s.value, ast.JoinedStr))


def fill_combined(tmpl: ast.JoinedStr, p1: str, p2: str) -> str:
    out = ""
    for v in tmpl.values:
        if isinstance(v, ast.Constant):
            out += v.value
        else:
            out += {"user_task_1": p1, "user_task_2": p2}[v.value.value.id]
    return out


def read_user_tasks() -> dict[str, dict]:
    hist: dict[str, list] = {}          # 클래스 → [(판, 정보)] — 조합 과업은 만든 판까지의 최신 구성 과업을 쓴다
    tmpl = combinator_prompt()
    for ver in VERSIONS:
        rel = f"default_suites/{ver}/{SUITE}/user_tasks.py"
        p = ROOT / rel
        if not p.exists():
            continue
        tree = ast.parse(p.read_text(encoding="utf-8"))
        mod = {}
        assigns(tree.body, mod)
        for c in tree.body:
            if isinstance(c, ast.ClassDef) and re.fullmatch(r"UserTask\d+", c.name):
                hist.setdefault(c.name, []).append((ver, parse_class(c, mod, ver, rel)))
        for x in ast.walk(tree):
            if isinstance(x, ast.Call) and isinstance(x.func, ast.Attribute) and x.func.attr in ("create_combined_task", "update_combined_task"):
                name = x.args[0].value
                comps = [m.value for a in x.args[1:3] for m in ast.walk(a)
                         if isinstance(m, ast.Constant) and isinstance(m.value, str) and re.fullmatch(r"user_task_\d+", m.value)]
                if any(k.arg == "prompt" for k in x.keywords):
                    raise SystemExit(f"{name}: prompt를 따로 준 조합 과업은 다루지 않는다")
                parts = [f"UserTask{c.split('_')[-1]}" for c in comps]
                subs = [hist[pc][-1][1] for pc in parts]          # 이 판까지의 최신
                info = {"ver": ver, "text": fill_combined(tmpl, subs[0]["text"], subs[1]["text"]),
                        "calls": subs[0]["calls"] + subs[1]["calls"], "url": f"{URL}/{rel}", "parts": parts}
                hist.setdefault(name, []).append((ver, info))
    return {k: v[-1][1] for k, v in hist.items()}


UT = read_user_tasks()


# ---------------------------------------------------------------------------
# 환경 YAML(include/*.yaml) — {자리}를 <<자리>>로 막아 읽고, 정상 기본값으로 채운다
# ---------------------------------------------------------------------------
def load(name: str):
    return yaml.safe_load(re.sub(r"\{(\w+)\}", r"<<\1>>", (DATA / "include" / name).read_text(encoding="utf-8")))


VEC = yaml.safe_load((DATA / "injection_vectors.yaml").read_text(encoding="utf-8"))
INBOX = load("inbox.yaml")
CAL = load("calendar.yaml")
DRIVE = load("cloud_drive.yaml")
FILES = {f["id_"]: f for f in DRIVE["initial_files"]}


def fill(text: str) -> str:
    return re.sub(r"<<(\w+)>>", lambda m: str(VEC[m.group(1)]["default"]), text)


def contacts() -> list[dict]:
    """AgentDojo Inbox._create_contact_list처럼 메일 주소에서 연락처를 만든다(이름 = @ 앞을 점→공백, 단어 첫 글자 대문자)."""
    seen, out = set(), []
    for e in INBOX["initial_emails"]:
        for a in [*e["recipients"], e["sender"], *(e.get("cc") or []), *(e.get("bcc") or [])]:
            if a not in seen:
                seen.add(a)
                out.append({"name": a.split("@")[0].replace(".", " ").title(), "email": a})
    return out


def event_txt(e: dict) -> str:
    return (f"Event: {e['title']}\nStart: {e['start_time']}  End: {e['end_time']}\nLocation: {e.get('location')}\n"
            f"Participants: {', '.join(e['participants'])}\nDescription: {fill(e.get('description') or '')}")


def file_txt(f: dict) -> str:
    return f"File: {f['filename']} (owner {f['owner']})\n{fill(f['content'])}"


def read_out(fn: str, a: dict) -> str:
    """읽기 호출이 돌려줄 글. AgentDojo 도구의 거르기 조건만 옮겨 적었다(일정: 제목·설명에 query, 날짜 일치 / 파일: 내용에 query)."""
    evs = CAL["initial_events"]
    if fn == "search_calendar_events":
        hit = [e for e in evs if (a.get("date") is None or e["start_time"].startswith(a["date"]))
               and (a["query"].lower() in e["title"].lower() or a["query"].lower() in fill(e.get("description") or "").lower())]
    elif fn == "get_day_calendar_events":
        hit = [e for e in evs if e["start_time"].startswith(a["day"])]
    elif fn == "search_contacts_by_name":
        return "\n".join(f"Name: {c['name']}  Email: {c['email']}" for c in contacts() if a["query"].lower() in c["name"].lower())
    elif fn == "search_files":
        return "\n\n".join(file_txt(f) for f in FILES.values() if a["query"].lower() in fill(f["content"]).lower())
    elif fn == "search_files_by_filename":
        return "\n\n".join(file_txt(f) for f in FILES.values() if a["filename"].lower() in f["filename"].lower())
    else:
        raise SystemExit(f"읽기 함수 {fn}의 출력을 만들 줄 모른다")
    if not hit:
        raise SystemExit(f"{fn}({a}): 맞는 일정이 없다")
    return "\n\n".join(event_txt(e) for e in hit)


# ---------------------------------------------------------------------------
# 도구 이름·인자 옮기기 (build_public_agentdojo.py 방식) — (새 이름, 새 인자, 옮김 설명 or None)
# ---------------------------------------------------------------------------
def fname(fid) -> str:
    return FILES[str(fid)]["filename"]


def to_gate(fn: str, a: dict) -> tuple[str, dict, str | None]:
    if fn == "search_calendar_events":
        return "list_events", {k: a[k] for k in ("query", "date") if k in a}, "search_calendar_events→list_events"
    if fn == "get_day_calendar_events":
        return "list_events", {"date": a["day"]}, "get_day_calendar_events→list_events(day→date)"
    if fn in ("search_contacts_by_name", "search_contacts_by_email"):
        return "search_contacts", {"query": a["query"]}, f"{fn}→search_contacts"
    if fn == "search_emails":
        return "list_mail", dict(a), "search_emails→list_mail"
    if fn == "get_unread_emails":
        return "list_mail", {"unread": True}, "get_unread_emails→list_mail(unread=True)"
    if fn == "get_received_emails":
        return "list_mail", {}, "get_received_emails→list_mail"
    if fn == "search_files":
        return "search_files", {"query": a["query"]}, None
    if fn == "search_files_by_filename":
        return "search_files", {"query": a["filename"]}, "search_files_by_filename→search_files(filename→query)"
    if fn == "get_file_by_id":
        return "read_doc", {"path": fname(a["file_id"])}, "get_file_by_id→read_doc(파일 id→파일 이름)"
    if fn == "list_files":
        return "list_files", {}, None
    if fn == "create_calendar_event":
        out = {"title": a["title"], "start": a["start_time"].replace(" ", "T"), "end": a["end_time"].replace(" ", "T")}
        out.update({k: a[k] for k in ("participants", "location", "description") if k in a})
        return "create_event", out, "create_calendar_event→create_event(start_time→start, end_time→end, 「 」→「T」)"
    if fn == "append_to_file":
        return "write_file", {"path": fname(a["file_id"]), "append": True, "content": a["content"]}, "append_to_file→write_file(append=True, 파일 id→파일 이름)"
    if fn == "create_file":
        return "write_file", {"path": a["filename"], "content": a["content"]}, "create_file→write_file(filename→path — 기존 빌더가 create_file 자리에 write_file을 씀)"
    if fn == "share_file":
        return "share_link", {"path": fname(a["file_id"]), "with": a["email"], "access": {"r": "read", "rw": "edit"}[a["permission"]]}, "share_file→share_link"
    if fn == "delete_file":
        return "delete_file", {"path": fname(a["file_id"])}, "delete_file(파일 id→파일 이름)"
    if fn == "delete_email":
        return "delete_mail", {"id": a["email_id"]}, "delete_email→delete_mail"
    if fn == "send_email":
        r = a["recipients"]
        out = {"to": r[0] if len(r) == 1 else r, "subject": a["subject"], "body": a["body"]}
        if a.get("attachments"):
            out["attach"] = [fname(x["file_id"] if isinstance(x, dict) else x) for x in a["attachments"]]
        return "send_email", out, "send_email(recipients→to, attachments→attach)"
    if fn in ("reschedule_calendar_event", "add_calendar_event_participants", "cancel_calendar_event", "get_current_day"):
        return fn, dict(a), f"문지기에 같은 도구가 없어 AgentDojo 이름 {fn}·인자 그대로"
    raise SystemExit(f"옮기는 법을 모르는 도구: {fn}")


def kind_of(fn: str) -> str:
    if fn in STATE:
        return "state"
    if fn.startswith(READ_PREFIX):
        return "read"
    raise SystemExit(f"상태 변경인지 모르는 함수: {fn}")


def call_str(name: str, args: dict) -> str:
    return f"{name}(" + ", ".join(f"{k}={v!r}" for k, v in args.items()) + ")"


def num(cls: str) -> int:
    return int(re.sub(r"\D", "", cls))


# ---------------------------------------------------------------------------
out, skipped = [], []
n = 800
for cls in sorted(UT, key=num):
    t = UT[cls]
    k = num(cls)
    if k in USED:
        continue
    if t["parts"] and any(num(p) in USED for p in t["parts"]):
        skipped.append(f"{cls}(조합 {'+'.join(t['parts'])} — 구성 과업이 앞 묶음에 쓰임)")
        continue
    idx = next((i for i, c in enumerate(t["calls"]) if kind_of(c["fn"]) == "state"), None)
    if idx is None:
        skipped.append(f"{cls}(읽기만)")
        continue
    calls = t["calls"][: idx + 1]
    if any(c["missing"] for c in calls):
        raise SystemExit(f"{cls}: 계산 인자 {[(c['fn'], c['missing']) for c in calls if c['missing']]} — 채우는 규칙이 필요")
    reads, call = calls[:idx], calls[idx]
    if any(kind_of(c["fn"]) != "read" for c in reads):
        raise SystemExit(f"{cls}: 첫 상태 변경 앞에 읽기가 아닌 호출")
    n += 1
    g_reads = [to_gate(c["fn"], c["args"]) for c in reads]
    name, args, how = to_gate(call["fn"], call["args"])
    src = "\n\n".join(f"[{call_str(g[0], g[1])}]\n{read_out(c['fn'], c['args'])}" for c, g in zip(reads, g_reads))
    why = [f"workspace {cls}(사용자 과업 원문 · AgentDojo {t['ver']})"]
    if t["parts"]:
        why.append(f"조합 과업({' + '.join(t['parts'])} — 문장·정답은 AgentDojo task_combinator 틀 그대로 이어 붙임)")
    why += [f"tool_call = 정답 호출의 첫 상태 변경 호출 {call['fn']}",
            "인자 값은 정답 코드의 글자 그대로" + (f" · {how}" if how else ""),
            f"actions_so_far = 그 앞의 정답 읽기 {len(reads)}건"]
    rhow = list(dict.fromkeys(g[2] for g in g_reads if g[2]))
    if rhow:
        why.append("읽기 이름 옮김: " + ", ".join(rhow))
    why.append("source_text = 그 읽기들이 돌려줄 환경 YAML 내용(주입 자리는 정상 기본값" + (f", {SRC_MAX}자에서 자름)" if len(src) > SRC_MAX else ")")
               if reads else "source_text 없음(앞선 읽기 없음)")
    out.append({
        "id": f"N{n}", "kind": "normal", "expect": "PASS",
        "origin": "AgentDojo", "origin_url": t["url"], "license": LICENSE, "set_note": SET_NOTE,
        "why": " · ".join(why),
        "user_request": t["text"], "actions_so_far": [call_str(g[0], g[1]) for g in g_reads],
        "tool_call": {"name": name, "args": args},
        "source_text": src if len(src) <= SRC_MAX else src[:SRC_MAX].rstrip() + "…",
    })

json.dump(out, sys.stdout, ensure_ascii=False, indent=1)
print()
from collections import Counter  # noqa: E402

print(f"정상 {len(out)}건 · 도구별 {dict(Counter(x['tool_call']['name'] for x in out))}", file=sys.stderr)
print("과업: " + ", ".join(f"{x['id']}={x['why'].split('(')[0].split()[-1]}" for x in out), file=sys.stderr)
print("뺀 것(앞 묶음 번호 말고): " + "; ".join(skipped), file=sys.stderr)
