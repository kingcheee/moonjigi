# 쓰는 법: python3 음절세기.py 읽는판.txt  (숫자·영문은 소리대로 한글로 적은 판을 넣는다 · #으로 시작하는 줄은 건너뜀)
import re,sys
def syl(s): return len(re.findall(r'[가-힣]', s))
lines=[l.rstrip('\n') for l in open(sys.argv[1]) if l.strip() and not l.startswith('#')]
tot=0
for i,l in enumerate(lines,1):
    n=syl(l); tot+=n; print(f"{i:>2} {n:>3}  {l}")
print("합계",tot, f"· 4.3음절/초 {tot/4.3:.1f}초 · 4.5음절/초 {tot/4.5:.1f}초")
