# -*- coding: utf-8 -*-
"""Claude Code 세션 로그에서 사용자 프롬프트 원본만 추출한다.
사용법:  python scrape_prompts.py clean.txt
"""
import json, os, glob, sys, collections

# CLAUDE_CONFIG_DIR로 설정 폴더를 옮긴 사람이 있다. 하드코딩하면 로그를 못 찾는데
# glob은 없는 경로에 빈 목록을 내놓아 "로그가 없다"와 구분되지 않는다.
_CONFIG   = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
PROJECTS  = os.path.join(_CONFIG, "projects")
OUT       = sys.argv[1] if len(sys.argv) > 1 else "clean.txt"
MAX_CHARS = 1200   # 프롬프트 1건 상한. 붙여넣은 로그·문서 전문이 파일을 삼키는 것을 막는다

NOISE = ("<command-", "<local-command", "<system-reminder", "Caveat:",
         "[Request interrupted", "Base directory for this skill:")

def texts(msg):
    c = msg.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "\n".join(x.get("text", "") for x in c
                         if isinstance(x, dict) and x.get("type") == "text")
    return ""

sessions, months, seen = [], collections.Counter(), collections.Counter()
for path in glob.glob(os.path.join(PROJECTS, "*", "*.jsonl")):
    project = os.path.basename(os.path.dirname(path))
    sid     = os.path.splitext(os.path.basename(path))[0]
    prompts, first = [], None
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if d.get("type") != "user" or d.get("isSidechain"):
                continue
            t = texts(d.get("message", {})).strip()
            if not t or t.startswith(NOISE):
                continue
            first = first or d.get("timestamp", "")[:10]
            if len(t) > MAX_CHARS:
                t = t[:MAX_CHARS] + f"\n…(이하 {len(t)-MAX_CHARS}자 생략 — 붙여넣기)"
            prompts.append(t)
    if not prompts:
        continue
    # 스케줄 루틴(자동 프롬프트 1건짜리)이 반복되면 첫 건만 남긴다.
    # len(prompts)==1 조건이 없으면 "STATE.md 읽고 이어서" 같은 재개 세션의 본문까지 날아간다
    key = prompts[0][:200]
    seen[key] += 1
    if seen[key] > 1 and len(prompts) == 1:
        sessions.append((project, first or "?", sid, ["(동일 자동 프롬프트 반복 — 본문 생략)"]))
    else:
        sessions.append((project, first or "?", sid, prompts))
    if first:
        months[first[:7]] += 1

sessions.sort(key=lambda s: (s[1], s[0]))
with open(OUT, "w", encoding="utf-8") as f:
    for project, date, sid, prompts in sessions:
        f.write(f"\n### [{project}] {date} {sid}\n\n")
        for p in prompts:
            f.write(p + "\n\n")

print(f"세션 {len(sessions)}개 / {os.path.getsize(OUT)/1024:.0f}KB -> {OUT}")
print("월별 분포 (30일 자동 정리로 잘려나갔는지 반드시 확인):")
for m in sorted(months):
    print(f"  {m}: {months[m]}건")
