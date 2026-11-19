# 쓰는 법: python3 이어읽기.py ../03-시연기술.md  (말할 대본 표에서 이어 읽기 판을 다시 만든다 · 박자 묶음 [1,2][3,4,5][6][7,8][9])
import re,sys
p=sys.argv[1]; s=open(p,encoding='utf-8').read()
sec=s.split('## 말할 대본')[1].split('### 이어 읽기')[0]
rows={}
for l in sec.splitlines():
    m=re.match(r'\| (\d) \| (.+?) \| (\d+) \|',l)
    if m: rows[int(m.group(1))]=(m.group(2),int(m.group(3)))
beats=[[1,2],[3,4,5],[6],[7,8],[9]]
body="\n>\n".join("> "+" ".join(rows[i][0] for i in b) for b in beats)
start='<!-- 이어읽기: 표에서 자동 생성 — 손으로 고치지 말고 표를 고친 뒤 다시 만든다 -->\n'
end='\n<!-- /이어읽기 -->'
new=re.sub(re.escape(start)+r'.*?'+re.escape(end), lambda m: start+body+end, s, flags=re.S)
print("표 음절 합", sum(v[1] for v in rows.values()), "· 줄", len(rows))
print("이어 읽기 변경 없음" if new==s else "이어 읽기를 표로 다시 만듦")
open(p,'w',encoding='utf-8').write(new)
sc=s.split('## 말할 대본')[1].split('【 】')[0]
print("말할 대본 쉼표", sum(r[0].count(',') for r in rows.values()), "· 대시", sum(r[0].count('—') for r in rows.values()))
