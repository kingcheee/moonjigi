#!/usr/bin/env python3
"""시연 영상 붙이기 — 장면별 mp4(record_demo.js) + 장면별 녹음 + 자막 글 → 영상 한 편.

  python3 tools/build_video.py --take <장면 mp4 폴더> --cues <자막.txt> [--audio <녹음 폴더>] --out <최종.mp4>
  python3 tools/build_video.py --extract-cues <대본.md> > 자막.txt     # 대본의 「### 장면 N」 아래 번호 줄로 자막 글 초안을 만든다

장면마다 따로 만든 뒤(화면 + 녹음 + 자막을 한 번에 인코딩) 다시 인코딩하지 않고 잇는다.

녹음  <녹음 폴더>/<N>.(m4a|wav|mp3|ogg|webm|aac|flac) — 장면 시작 --lead초 뒤에 얹는다. 없는 장면은 무음.
      녹음이 장면보다 길면 그 장면 끝 화면을 멈춘 채 늘린다(⚠ 표시 · 전체 길이가 는다).
자막  자막.txt — 「[N]」 줄 아래에 자막 한 장씩 한 줄. 시간을 안 적으면 녹음 길이(없으면 장면 길이)에
      글자 수 비율로 나눠 띄운다. 직접 정하려면 줄 앞에 「1.2-3.5 」(장면 시작 기준 초)를 붙인다 —
      한 장면 안에서는 전부 적거나 전부 비운다. 「#」로 시작하는 줄은 무시한다.
결과  최종 mp4(1920×1080 · 30fps · H.264 · AAC · faststart) + 같은 이름의 .srt(전체 자막) + 길이 보고.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

AUDIO_EXT = (".m4a", ".wav", ".mp3", ".ogg", ".webm", ".aac", ".flac")
# 화면 맨 아래 입력 줄 위에 반투명 상자로 — 결정 띠 · 「끝난 뒤」(보낸 메일 0통 · 차단 27건)를 가리지 않는다(18:3x 장면 끝 프레임으로 확인).
# FontSize=20 · MarginV=40은 「끝난 뒤」를 덮었다.
STYLE = "FontName=Pretendard,FontSize=13,Bold=1,BorderStyle=3,Outline=6,Shadow=0,BackColour=&H33000000,OutlineColour=&H33000000,MarginV=4"
SLOT = 100.0          # 발표 3장에 잡힌 영상 자리(초)
TAIL = 0.4            # 녹음이 끝난 뒤 장면을 넘기기 전 여유(초)


def probe(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
                         check=True, capture_output=True, text=True).stdout
    return float(json.loads(out)["format"]["duration"])


def extract_cues(md: Path) -> str:
    out, scene = [], None
    for line in md.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^###\s*장면\s*(\d+)", line)
        if m:
            scene = int(m.group(1)); out.append(f"\n[{scene}]"); continue
        if line.startswith("#"):
            scene = None; continue
        m = re.match(r"^\d+\.\s+(.+)$", line.strip())
        if scene is not None and m:
            out.append(m.group(1).strip())
    head = "# 자막 글 — [장면 번호] 아래 한 줄 = 자막 한 장. 시간은 비워 두면 녹음 길이에 맞춰 나눈다.\n"
    return head + "\n".join(out).lstrip("\n") + "\n"


def parse_cues(path: Path) -> dict[int, list[tuple[float | None, float | None, str]]]:
    cues: dict[int, list] = {}
    scene = None
    for k, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^\[(\d+)\]$", line)
        if m:
            scene = int(m.group(1)); cues.setdefault(scene, []); continue
        if scene is None:
            sys.exit(f"{path}:{k}: [장면 번호] 줄보다 앞에 자막이 있다")
        m = re.match(r"^(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s+(.+)$", line)
        cues[scene].append((float(m.group(1)), float(m.group(2)), m.group(3)) if m else (None, None, line))
    for n, cs in cues.items():
        timed = {c[0] is not None for c in cs}
        if len(timed) > 1:
            sys.exit(f"{path}: 장면 {n}에 시간을 적은 줄과 안 적은 줄이 섞여 있다 — 전부 적거나 전부 비운다")
    return cues


def weight(text: str) -> int:
    return max(1, len(re.sub(r"\s", "", text)))


def time_cues(cs, start: float, span: float):
    """시간 없는 자막을 [start, start+span]에 글자 수 비율로 나눈다."""
    if not cs or cs[0][0] is not None:
        return [(a, b, t) for a, b, t in cs]
    total = sum(weight(t) for _, _, t in cs)
    out, t0 = [], start
    for _, _, text in cs:
        d = span * weight(text) / total
        out.append((t0, t0 + d, text)); t0 += d
    return out


def srt_time(s: float) -> str:
    ms = int(round(s * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def write_srt(path: Path, cues) -> None:
    lines = []
    for i, (a, b, text) in enumerate(cues, 1):
        lines += [str(i), f"{srt_time(a)} --> {srt_time(b)}", text, ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def find_audio(d: Path | None, n: int) -> Path | None:
    if not d:
        return None
    for ext in AUDIO_EXT:
        p = d / f"{n}{ext}"
        if p.is_file():
            return p
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="시연 영상 붙이기")
    ap.add_argument("--extract-cues", type=Path, help="대본 md에서 자막 글 초안을 뽑아 stdout으로")
    ap.add_argument("--take", type=Path, help="scene-N.mp4가 든 폴더(record_demo.js --out)")
    ap.add_argument("--cues", type=Path, help="자막 글 파일")
    ap.add_argument("--audio", type=Path, help="장면별 녹음 폴더(<N>.m4a 등) — 없어도 된다")
    ap.add_argument("--out", type=Path, help="최종 mp4")
    ap.add_argument("--scenes", default="1,2,3,4,5")
    ap.add_argument("--lead", type=float, default=0.3, help="장면 시작에서 녹음이 시작하기까지(초)")
    ap.add_argument("--no-subs", action="store_true", help="자막을 굽지 않는다(.srt는 그대로 쓴다)")
    ap.add_argument("--style", default=STYLE, help="자막 모양(libass force_style) — 기본은 맨 아래 반투명 상자")
    a = ap.parse_args()

    if a.extract_cues:
        sys.stdout.write(extract_cues(a.extract_cues)); return 0
    if not (a.take and a.out):
        ap.error("--take와 --out이 필요하다")

    scenes = [int(x) for x in a.scenes.split(",") if x.strip()]
    cues = parse_cues(a.cues) if a.cues else {}
    work = a.out.parent / f"build-{a.out.stem}"
    work.mkdir(parents=True, exist_ok=True)

    report, warns, all_cues, segs, offset = [], [], [], [], 0.0
    for n in scenes:
        vid = a.take / f"scene-{n}.mp4"
        if not vid.is_file():
            sys.exit(f"장면 {n} 영상이 없다: {vid}")
        vdur = probe(vid)
        aud = find_audio(a.audio, n)
        adur = probe(aud) if aud else 0.0
        need = a.lead + adur + TAIL if aud else 0.0
        seg = max(vdur, need)
        ext = seg - vdur
        span_start = a.lead if aud else 0.3
        span = adur if aud else max(0.5, vdur - 0.6)
        cs = time_cues(cues.get(n, []), span_start, span)
        for c0, c1, text in cs:
            if c1 > seg + 1e-6:
                warns.append(f"장면 {n}: 자막 「{text[:16]}…」이 장면 끝({seg:.1f}초)을 넘는다({c1:.1f}초)")
        srt = work / f"s{n}.srt"
        write_srt(srt, cs)
        all_cues += [(offset + c0, offset + c1, t) for c0, c1, t in cs]

        vf = f"[0:v]tpad=stop_mode=clone:stop_duration={ext:.3f},fps=30,scale=1920:1080:flags=lanczos:out_range=tv"
        if cs and not a.no_subs:
            vf += f",subtitles={srt.name}:force_style='{a.style}'"
        vf += ",format=yuv420p[v]"
        if aud:
            af = f"[1:a]aresample=48000,aformat=channel_layouts=stereo,adelay={int(a.lead * 1000)}:all=1,apad[a]"
            ain = ["-i", str(aud.resolve())]
        else:
            af = "[1:a]anull[a]"
            ain = ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
        out = work / f"seg-{n}.mp4"
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(vid.resolve()), *ain,
                        "-filter_complex", f"{vf};{af}", "-map", "[v]", "-map", "[a]", "-t", f"{seg:.3f}",
                        "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-r", "30", "-pix_fmt", "yuv420p", "-color_range", "tv",
                        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", out.name],
                       check=True, cwd=work)
        segs.append(out)
        flag = f" ⚠ 녹음이 길어 화면을 {ext:.1f}초 늘림" if ext > 0.05 else ""
        report.append(f"장면 {n}: 화면 {vdur:5.1f}초 · 녹음 {adur:5.1f}초{'' if aud else '(없음 · 무음)'} · 결과 {seg:5.1f}초 · 자막 {len(cs)}장{flag}")
        offset += seg

    (work / "segs.txt").write_text("".join(f"file '{s.name}'\n" for s in segs), encoding="utf-8")
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", "segs.txt",
                    "-c", "copy", "-movflags", "+faststart", str(a.out.resolve())], check=True, cwd=work)
    write_srt(a.out.with_suffix(".srt"), all_cues)

    total = probe(a.out)
    print("\n".join(report))
    print(f"합계 {total:.1f}초 (3장 자리 {SLOT:.0f}초)" + (f"  ⚠⚠ {total - SLOT:.1f}초 넘침 — 녹음을 줄이거나 발표 시간표를 고친다" if total > SLOT + 0.5 else ""))
    for w in warns:
        print("⚠ " + w)
    print(f"→ {a.out}\n→ {a.out.with_suffix('.srt')}\n(중간 파일: {work})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
