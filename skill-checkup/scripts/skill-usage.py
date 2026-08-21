# -*- coding: utf-8 -*-
"""세션 로그에서 스킬 로드 횟수를 센다.

세는 신호는 세션 jsonl에 남는 "Base directory for this skill: <경로>" 한 줄이다.
명시 호출(Skill 도구)과 자동 발동(description 매칭)을 모두 잡는다.

못 세는 것 — 결과를 읽을 때 반드시 함께 본다:
  - 다른 하네스(codex 등)에서 링크해 쓴 발동. 그쪽 로그는 이 디렉터리에 없다
  - 서브에이전트 레인 안의 발동. 메인 jsonl에 안 들어온다(기본 제외, --with-subagents로 포함)
  - cleanupPeriodDays로 이미 지워진 기간. 받는 쪽 기본값은 30일이라 --days를 그보다
    크게 줘도 실제 창은 30일이다. 출력의 "기간"이 실제 창이다
  - --days는 파일 수정시각 기준이다. 옛 세션을 --resume하면 그 세션의 오래된 발동이
    통째로 창 안에 들어온다. 반대로 창 안에서 시작된 대화만 세지도 않는다

부풀리는 것:
  - 감지 문자열을 화면에 찍은 세션은 자기가 분자에 섞인다(로그를 분석·디버깅한 세션)

사용: python skill-usage.py [--days N] [--with-subagents]
"""
import os, re, sys, json, io, time
from collections import Counter

# stdout이 리다이렉트되면 Windows에서 로케일 코드페이지로 인코딩된다.
# 한글 키를 쓰므로 비한글 로케일에서 UnicodeEncodeError로 죽는다.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# CLAUDE_CONFIG_DIR로 설정 폴더를 옮긴 사람이 있다. 하드코딩하면 로그를 못 찾고,
# os.walk은 없는 디렉터리에 조용히 아무것도 안 내놓는다 — "안 돌았다"와 출력이 같아진다.
CONFIG = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
ROOT = os.path.join(CONFIG, "projects")

SEP = "[/" + chr(92) + chr(92) + "]+"   # 문자 클래스 안에서 백슬래시는 두 개여야 리터럴이 된다

# 경로의 **마지막 조각**을 잡는다. "skills 다음 조각"으로 잡으면 플러그인 캐시 경로
# (<캐시>/<마켓플레이스>/<플러그인>/<버전>/<스킬>)에서 마켓플레이스 이름에 skills가
# 들어갈 때 거기서 매치되어 플러그인 이름을 스킬명으로 착각한다. 경로 끝은 jsonl
# 이스케이프(\r, \n) 아니면 문자열 종료(")다.
PAT = re.compile('Base directory for this skill:[^"]*?' + SEP
                 + '([A-Za-z0-9._-]+)(?=' + chr(92) * 2 + '[rn]|")')

# 스킬 폴더명 규약: kebab-case 소문자, 두 글자 이상.
NAME_OK = re.compile(r"^[a-z][a-z0-9]+(-[a-z0-9]+)*$")

# 훅 주입은 스킬 파일 로드 없이도 절차를 시작시킨다. 로드만 세면 훅으로 도는
# 스킬의 발동률을 크게 과소평가하므로 따로 센다. 마커는 각 훅이 내보내는 문구이며
# **훅 파일에서 확인하고 넣는다.** 자기 훅을 만들었으면 여기에 추가한다.
HOOK_MARKERS = {
    "senior-mentor(훅)": re.compile(r"\[이해 확인 대상\]|\[복습 대상\]"),
    "cs-drill(훅)": re.compile(r"\[CS 복습\]"),
}

days = None
with_sub = "--with-subagents" in sys.argv
if "--days" in sys.argv:
    i = sys.argv.index("--days") + 1
    if i >= len(sys.argv):
        sys.exit("--days 뒤에 일수를 줘야 한다")
    days = int(sys.argv[i])
cutoff = time.time() - days * 86400 if days else None

if not os.path.isdir(ROOT):
    sys.exit("로그 디렉터리를 못 찾았다: " + ROOT
             + "\nCLAUDE_CONFIG_DIR을 쓰고 있으면 그 값이 맞는지 확인한다.")

loads, sessions, per_project, dropped = Counter(), 0, Counter(), Counter()
sessions_with = Counter()   # 스킬별 "발동한 세션 수" — 한 세션에서 여러 번 로드돼도 1
oldest = newest = None

# 훅을 아예 안 건 것과 훅이 한 번도 안 울린 것을 가르려면 0인 행이 남아야 한다.
for label in HOOK_MARKERS:
    loads.setdefault(label, 0)
    sessions_with.setdefault(label, 0)

for dirpath, _, files in os.walk(ROOT):
    if not with_sub and "subagents" in dirpath.replace(chr(92), "/").split("/"):
        continue
    for fn in files:
        if not fn.endswith(".jsonl"):
            continue
        p = os.path.join(dirpath, fn)
        try:
            mt = os.path.getmtime(p)
        except OSError:
            continue
        if cutoff and mt < cutoff:
            continue
        sessions += 1
        oldest = mt if oldest is None else min(oldest, mt)
        newest = mt if newest is None else max(newest, mt)
        per_project[os.path.relpath(dirpath, ROOT).split(os.sep)[0]] += 1
        try:
            text = io.open(p, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        raw = PAT.findall(text)
        # 스킬 이름은 kebab-case 소문자다. 여기 안 맞는 것은 이스케이프가 여러 겹인
        # 인용문에서 나온 파편이라 거른다. 조용히 버리지 않고 아래 "거른 것"에 남긴다.
        found = [n for n in raw if NAME_OK.match(n)]
        for n in raw:
            if not NAME_OK.match(n):
                dropped[n] += 1
        for name in found:
            loads[name] += 1
        for name in set(found):
            sessions_with[name] += 1
        for label, pat in HOOK_MARKERS.items():
            hits = len(pat.findall(text))
            if hits:
                loads[label] += hits
                sessions_with[label] += 1


def fmt(t):
    return time.strftime("%Y-%m-%d", time.localtime(t)) if t else "-"


out = {
    "세션수": sessions,
    "기간": {"처음": fmt(oldest), "마지막": fmt(newest)},
    "로그경로": ROOT,
    "서브에이전트포함": with_sub,
    "스킬별로드": dict(loads.most_common()),
    "스킬별발동세션수": {k: sessions_with[k] for k, _ in loads.most_common()},
    "프로젝트별세션수": dict(per_project.most_common(10)),
    "쓴훅마커": {k: v.pattern for k, v in HOOK_MARKERS.items()},
    "못세는것": [x for x in [
        "다른 하네스(codex 등)의 발동",
        None if with_sub else "서브에이전트 레인 내부",
        "cleanupPeriodDays로 삭제된 기간 — 출력의 '기간'이 실제 창이다",
        "--days는 파일 수정시각 기준이라 재개한 옛 세션이 창 안으로 들어온다",
    ] if x],
    "부풀리는것": ["감지 문자열을 화면에 찍은 세션은 자기가 분자에 섞인다"],
    "거른것": dict(dropped.most_common(10)),
}

# 점검을 돌리는 세션은 방금 이 스킬을 로드했다. 세션이 있는데 로드가 0건이면
# 스킬이 안 돈 것이 아니라 감지 문자열이 안 맞는 것이다.
real = {k: v for k, v in loads.items() if v and k not in HOOK_MARKERS}
if sessions and not real:
    out["경고"] = ("세션은 있는데 스킬 로드가 0건이다 — 감지 문자열이 하네스와 안 맞는 것으로 본다. "
                 "이 수치로 트리거를 고치지 마라.")

print(json.dumps(out, ensure_ascii=False, indent=2))
