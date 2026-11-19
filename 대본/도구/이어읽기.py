# 쓰는 법: python3 이어읽기.py ../03-시연기술.md
#   「말할 대본」 표에서 이어 읽기 판(본문 안 <!-- 이어읽기 --> 구간)과 읽는 판(03-시연기술-읽는판.md)을 다시 만든다.
#   박자 묶음은 본문의 <!-- 박자: 1,2 | 3,4,5,6 | ... --> 줄에서 읽는다. 표의 줄 수와 박자의 줄 수가 다르면 멈춘다.
import re, sys, os

p = sys.argv[1]
s = open(p, encoding='utf-8').read()
sec = s.split('## 말할 대본')[1].split('### 이어 읽기')[0]
rows = {}
for l in sec.splitlines():
    m = re.match(r'\| (\d+) \| (.+?) \| (\d+) \|', l)
    if m:
        rows[int(m.group(1))] = (m.group(2), int(m.group(3)))
bm = re.search(r'<!-- 박자: (.+?) -->', s)
assert bm, '박자 줄이 없다'
beats = [[int(x) for x in g.split(',')] for g in bm.group(1).split('|')]
flat = [i for b in beats for i in b]
assert sorted(flat) == sorted(rows) == list(range(1, len(rows) + 1)), f'표 {sorted(rows)} · 박자 {flat}'
body = "\n>\n".join("> " + " ".join(rows[i][0] for i in b) for b in beats)
start = '<!-- 이어읽기: 표에서 자동 생성 — 손으로 고치지 말고 표를 고친 뒤 다시 만든다 -->\n'
end = '\n<!-- /이어읽기 -->'
new = re.sub(re.escape(start) + r'.*?' + re.escape(end), lambda m: start + body + end, s, flags=re.S)
open(p, 'w', encoding='utf-8').write(new)
title = re.search(r'<!-- 읽는판 제목: (.+?) -->', s)
out = "# " + (title.group(1) if title else "읽는 판") + "\n\n" + "\n\n".join("\n".join(rows[i][0] for i in b) for b in beats) + "\n"
rp = os.path.join(os.path.dirname(os.path.abspath(p)), '03-시연기술-읽는판.md')
open(rp, 'w', encoding='utf-8').write(out)
print("표 음절 합", sum(v[1] for v in rows.values()), "· 줄", len(rows), "· 이어 읽기", "그대로" if new == s else "다시 만듦", "· 읽는 판 씀")
print("말할 대본 쉼표", sum(r[0].count(',') for r in rows.values()), "· 대시", sum(r[0].count('—') for r in rows.values()))
