#!/usr/bin/env python3
"""장면 mp4에 살짝 확대·이동(켄 번스)을 입힌다 — 11-04 중간발표 편집(1.3～1.6배)보다 약하게 1.0～1.3배.

  python3 zoom_scenes.py <take 폴더> <출력 폴더>

키프레임 (초, 배율, 중심 x, 중심 y) — 좌표는 1920×1080 원본 프레임 기준.
키프레임 사이는 smoothstep으로 이어서 「들어가고·머물고·빠지는」 움직임이 끊기지 않는다.
들어간 뒤에는 고정한다(사용자 11-20: 자주·빠르게 말고 판단이 뜨는 곳에만 확실하게).
출력 폴더에 scene-N.mp4를 쓰므로 build_video.py --take 로 그대로 넘기면 자막이 위에 얹힌다.
"""
import subprocess, sys
from pathlib import Path
import numpy as np
from PIL import Image

W, H, FPS = 1920, 1080, 30
C = (960, 540)

KEYS = {
    # 확대는 「모델의 판단」이 화면에 뜨는 곳에만 — 장면당 1～2번, 1.5초에 걸쳐 들어가고 들어간 뒤엔 고정.
    # 1 정상 작업 — 툴 호출 두 줄의 「통과 0.07초」 판정
    1: [(0, 1.0, *C), (3.0, 1.0, *C), (4.5, 1.16, 1290, 440), (10, 1.16, 1290, 440)],
    # 2 오작동 — 차단 리스트 + 「27통 무단 삭제 시도를 모두 멈췄습니다」 판정 띠
    2: [(0, 1.0, *C), (4.5, 1.0, *C), (6.0, 1.15, 1280, 450), (20, 1.15, 1280, 450)],
    # 3 인젝션 — 판별 상세의 점수(인젝션 0.12 · 요청 일치 0.03) → 디시전 헤드 0.31초 차단 판정
    3: [(0, 1.0, *C), (7.0, 1.0, *C), (8.2, 1.28, 1640, 440), (12.6, 1.28, 1640, 440),
        (13.8, 1.18, 1040, 600), (17.6, 1.18, 1040, 600)],
    # 4 정책 위반 — 계좌번호 메일 · 「한 번 더 따져 보는」 판정 → (정책 켜는 동안은 전체 화면) → 사내 정책 사유가 붙은 판정 · 보낸 메일 0통
    4: [(0, 1.0, *C), (4.5, 1.0, *C), (6.0, 1.15, 1300, 600), (10.0, 1.15, 1300, 600), (13.0, 1.15, 1300, 520),
        (15.0, 1.15, 1300, 520), (16.5, 1.0, *C), (23.5, 1.0, *C), (25.0, 1.15, 1200, 680), (30, 1.15, 1200, 680)],
    # 5 MCP — 감사 로그에 쌓이는 판정(통과 · 보류 + 사유)
    5: [(0, 1.0, *C), (4.5, 1.0, *C), (6.0, 1.2, 880, 580), (25, 1.2, 880, 580)],
}


# 장면 길이(초) — 녹음을 얹으면서 장면 1·5 끝(정지 화면)에서 떼어 장면 3에 준다(place_voice.py의 DUR과 같아야 한다)
DUR = {1: 8.2, 2: 20.0, 3: 17.6, 4: 30.0, 5: 24.2}

# 하이라이트 박스 — 대사가 가리키는 「판단」에 (시작, 끝, x0, y0, x1, y1), 원본 1920×1080 좌표. 시각은 자막-음성.txt(말하는 시각) 기준.
BOX = {
    1: [(3.0, 7.0, 780, 344, 1776, 436)],                      # 툴 호출 두 줄 — 0.07초 · 통과
    2: [(12.6, 18.4, 780, 456, 1776, 616)],                    # 「27통 무단 삭제 시도를 모두 멈췄습니다」 · 요청하지 않은 작업
    3: [(7.2, 9.35, 1406, 386, 1876, 436),                     # 인젝션 유래 여부 0.12
        (9.45, 12.85, 1406, 320, 1876, 370),                   # 요청 의도 일치도 0.03
        (13.0, 17.6, 680, 524, 1356, 710)],                    # 차단 판정 띠 0.31초
    4: [(8.8, 11.4, 783, 734, 1778, 882),                      # 심층 추론 — 한 번 더 따져 보는 중
        (12.0, 15.7, 780, 486, 1776, 690),                     # 확신 부족 → 사람 확인 요청
        (16.4, 20.8, 780, 176, 1776, 262),                     # 사내 정책 문장
        (23.9, 27.0, 780, 492, 1776, 674),                     # 사내 정책 위반 판정
        (24.4, 29.6, 776, 788, 1100, 822)],                    # 발송한 메일 0통
    5: [(7.2, 9.4, 290, 516, 1430, 572),                       # 감사 로그에 쌓이는 판정
        (13.4, 19.6, 290, 516, 1430, 572)],                    # 메일 발송 보류 · 사내 정책 · 계좌번호
}
BOX_RGB = (255, 145, 0)   # 주황 — 파란 UI 위에서 튄다


def draw_boxes(im, boxes, t):
    from PIL import ImageDraw
    over = None
    for t0, t1, x0, y0, x1, y1 in boxes:
        a = min(1.0, max(0.0, (t - t0) / 0.3), max(0.0, (t1 - t) / 0.3))
        if a <= 0: continue
        if over is None:
            over = Image.new("RGBA", im.size, (0, 0, 0, 0)); d = ImageDraw.Draw(over)
        pad = 8
        d.rounded_rectangle((x0 - pad, y0 - pad, x1 + pad, y1 + pad), radius=12,
                            fill=(*BOX_RGB, int(28 * a)), outline=(*BOX_RGB, int(255 * a)), width=5)
    if over is None: return im
    return Image.alpha_composite(im.convert("RGBA"), over).convert("RGB")


def ss(u):
    u = min(1.0, max(0.0, u)); return u * u * (3 - 2 * u)


def at(keys, t):
    if t <= keys[0][0]: return keys[0][1:]
    for (t0, *a), (t1, *b) in zip(keys, keys[1:]):
        if t <= t1:
            k = ss((t - t0) / (t1 - t0))
            return tuple(x + (y - x) * k for x, y in zip(a, b))
    return keys[-1][1:]


def scene(src: Path, dst: Path, keys, boxes=(), dur=None):
    dec = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(src), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                            "-c:v", "libx264", "-crf", "16", "-preset", "medium", "-pix_fmt", "yuv420p", str(dst)], stdin=subprocess.PIPE)
    n, last, total = 0, None, int(round((dur or 1e9) * FPS))
    while n < total:
        buf = dec.stdout.read(W * H * 3)
        if len(buf) < W * H * 3:
            if last is None or dur is None: break
            buf = last                                   # 녹음이 화면보다 길면 마지막 프레임을 이어 붙인다
        last = buf
        z, cx, cy = at(keys, n / FPS)
        cw, ch = W / z, H / z
        x0 = min(max(cx - cw / 2, 0), W - cw); y0 = min(max(cy - ch / 2, 0), H - ch)
        im = draw_boxes(Image.frombuffer("RGB", (W, H), buf), boxes, n / FPS)
        if z > 1.0005:
            im = im.resize((W, H), Image.LANCZOS, box=(x0, y0, x0 + cw, y0 + ch))
        enc.stdin.write(im.tobytes()); n += 1
    enc.stdin.close(); enc.wait(); dec.kill(); dec.wait()
    print(f"{dst.name}: {n} 프레임 ({n / FPS:.2f}초)")


if __name__ == "__main__":
    take, out = Path(sys.argv[1]), Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
    only = [int(x) for x in sys.argv[3].split(",")] if len(sys.argv) > 3 else list(KEYS)
    import concurrent.futures as cf
    with cf.ThreadPoolExecutor(5) as ex:
        list(ex.map(lambda n: scene(take / f"scene-{n}.mp4", out / f"scene-{n}.mp4", KEYS[n], BOX.get(n, ()), DUR[n]), only))
