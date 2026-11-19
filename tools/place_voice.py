#!/usr/bin/env python3
"""한 번에 녹음한 대본(대본녹음.m4a)을 문장별로 잘라 각 장면의 자막 시각에 얹는다.
  → <출력 폴더>/<N>.wav (장면 길이 - 0.45초, build_video.py --audio · --lead 0 으로 넘긴다)
  → <자막 출력.txt> (실제 말하는 시각에 맞춘 자막 — 글도 녹음대로)
문장 구간은 faster-whisper(small) 받아쓰기의 시각(11-20 08:2x)."""
import subprocess
from pathlib import Path
# python3 place_voice.py <대본녹음.m4a> <장면별 출력 폴더> <자막 출력.txt>
import sys
SRC, OUT, CUES = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]); OUT.mkdir(parents=True, exist_ok=True)
DUR = {1: 8.2, 2: 20.0, 3: 17.6, 4: 30.0, 5: 24.2}   # 장면 3은 말이 빽빽해 1·5장면 끝(정지 화면)에서 2.6초를 떼어 준다
PRE, POST, GAP, END_ROOM = 0.10, 0.18, 0.15, 0.40
# (장면, 원하는 시작, 녹음 시작, 녹음 끝, 자막 글)
L = [
 (1, 0.3, 2.02, 4.02, "먼저 정상 작업입니다."),
 (1, 2.3, 4.66, 8.42, "회의록을 옮기는 툴 호출 두 번은 지연 없이 바로 통과합니다."),
 (2, 0.3, 9.32, 11.28, "답장만 시켰고, 공격자는 없습니다."),
 (2, 4.0, 12.28, 16.20, "하지만 에이전트의 해석이 고객 메일 27통을 지우려 합니다."),
 (2, 11.5, 17.14, 20.88, "문지기가 이건 되돌리기 어려우며, 시키지 않은 작업이라 보고"),
 (2, 15.6, 20.88, 22.88, "27건을 모두 막았습니다."),
 (3, 0.3, 24.44, 26.14, "웹페이지 요약을 시킨 기록입니다."),
 (3, 2.6, 26.86, 29.98, "숨은 지시대로 에이전트가 폴더 삭제를 불렀습니다."),
 (3, 6.6, 30.16, 33.18, "외부 지시인지는 0.12로 놓쳤지만"),
 (3, 9.7, 33.18, 36.26, "시킨 일인지에 대한 확률이 0.03이라"),
 (3, 12.0, 36.26, 40.30, "Zoro-1의 디시전 헤드가 0.3초 만에 이 행동을 막았습니다."),
 (4, 0.3, 41.86, 45.98, "에이전트가 메일 끝 안내대로 남의 계좌번호를 답장에 넣었습니다."),
 (4, 5.2, 47.02, 50.50, "이 행동이 잘못되었는지 포인터 헤드가 애매하다고 판단해,"),
 (4, 9.2, 50.50, 52.62, "thinking이 켜져 다시 판정됩니다."),
 (4, 12.0, 52.86, 56.02, "그래도 확신이 없어 사람에게 승인을 요청합니다."),
 (4, 16.2, 56.94, 60.92, "사내 정책을 추가하여 계좌번호를 보내면 안 된다는 이유가 생기면,"),
 (4, 23.2, 60.92, 63.20, "보내지는 메일은 0통이 됩니다."),
 (5, 0.3, 64.54, 66.62, "문지기는 MCP 서버로도 동작합니다."),
 (5, 4.5, 67.54, 71.82, "지금 pi 에이전트가 다른 모델(Nemotron)을 쓰면 툴 호출이 한 줄씩 쌓입니다."),
 (5, 15.0, 72.72, 76.58, "문지기 MCP는 이 툴에 붙어 안전을 챙겨주는 게이트입니다."),
]
cues_txt, placed = [], {}
for n in DUR:
    rows = [r for r in L if r[0] == n]
    clips = [(max(0, a - PRE), b + POST) for _, _, a, b, _ in rows]
    st = [r[1] for r in rows]
    for i in range(1, len(st)):                       # 앞 문장과 겹치지 않게 뒤로
        st[i] = max(st[i], st[i - 1] + (clips[i - 1][1] - clips[i - 1][0]) + GAP)
    lim = DUR[n] - END_ROOM
    for i in range(len(st) - 1, -1, -1):              # 장면 끝을 넘으면 앞으로 당긴다
        d = clips[i][1] - clips[i][0]
        nxt = st[i + 1] - GAP if i + 1 < len(st) else lim
        st[i] = min(st[i], nxt - d)
    assert st[0] >= 0, (n, st)
    placed[n] = list(zip(st, clips, [r[4] for r in rows]))
    # 장면 녹음 파일: 문장들을 제자리에
    ins, fc = [], []
    for k, (s, (a, b), _) in enumerate(placed[n]):
        ins += ["-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", str(SRC)]
        fc.append(f"[{k}:a]aresample=48000,adelay={int(s * 1000)}:all=1[a{k}]")
    fc.append("".join(f"[a{k}]" for k in range(len(placed[n]))) + f"amix=inputs={len(placed[n])}:normalize=0,apad,atrim=0:{lim:.3f}[o]")
    subprocess.run(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", ";".join(fc), "-map", "[o]", "-ar", "48000", str(OUT / f"{n}.wav")], check=True)
    cues_txt.append(f"[{n}]")
    for k, (s, (a, b), t) in enumerate(placed[n]):
        e = min(s + (b - a) + 0.25, placed[n][k + 1][0] if k + 1 < len(placed[n]) else DUR[n])
        cues_txt.append(f"{s:.2f}-{e:.2f} {t}")
        print(f"장면 {n}  {s:5.2f}-{e:5.2f}  {t}")
    cues_txt.append("")
CUES.write_text("\n".join(cues_txt), encoding="utf-8")
