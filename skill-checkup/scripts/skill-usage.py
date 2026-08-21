# -*- coding: utf-8 -*-
"""세션 로그에서 스킬 로드 횟수를 센다.

세는 신호는 세션 jsonl에 남는 "Base directory for this skill: <경로>" 한 줄이다.
명시 호출(Skill 도구)과 자동 발동(description 매칭)을 모두 잡는다.

못 세는 것 — 결과를 읽을 때 반드시 함께 본다:
  - 다른 하네스(codex 등)에서 링크해 쓴 발동. 그쪽 로그는 ~/.claude/projects에 없다
  - 서브에이전트 레인 안의 발동. 메인 jsonl에 안 들어온다(기본 제외, --with-subagents로 포함)
  - cleanupPeriodDays로 이미 지워진 기간

사용: python skill-usage.py [--days N] [--with-subagents]
"""
import os, re, sys, json, io, time
from collections import Counter

ROOT = os.path.join(os.path.expanduser("~"), ".claude", "projects")

# 경로 구분자가 Windows 백슬래시라 소스에 리터럴로 두면 이스케이프가 꼬인다.
# chr(92)로 런타임 조립한다.
SEP = "[/" + chr(92) + chr(92) + "]+"   # 문자 클래스 안에서 백슬래시는 두 개여야 리터럴이 된다
PAT = re.compile('Base directory for this skill:[^"]*?skills' + SEP + '([A-Za-z0-9._-]+)')

# 훅 주입은 스킬 파일 로드 없이도 절차를 시작시킨다. 로드만 세면 훅으로 도는
# 스킬의 발동률을 크게 과소평가하므로 따로 센다. 마커는 각 훅이 내보내는 문구다.
HOOK_MARKERS = {
    "senior-mentor(훅)": re.compile(r"\[예측 대조\]|\[복습 대상\]"),
    "cs-drill(훅)": re.compile(r"\[CS 복습\]"),
}

days = None
with_sub = "--with-subagents" in sys.argv
if "--days" in sys.argv:
    days = int(sys.argv[sys.argv.index("--days") + 1])
cutoff = time.time() - days * 86400 if days else None

loads, sessions, per_project = Counter(), 0, Counter()
sessions_with = Counter()   # 스킬별 "발동한 세션 수" — 한 세션에서 여러 번 로드돼도 1
oldest = newest = None

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
        # 플러그인 캐시 경로에 버전 디렉터리(2.1.233 등)가 섞여 스킬명처럼 잡힌다. 걸러낸다.
        found = [n for n in PAT.findall(text) if not re.fullmatch(r"[0-9.]+", n)]
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
    "서브에이전트포함": with_sub,
    "스킬별로드": dict(loads.most_common()),
    "스킬별발동세션수": dict(sessions_with.most_common()),
    "프로젝트별세션수": dict(per_project.most_common(10)),
    "못세는것": [x for x in [
        "다른 하네스(codex 등)의 발동",
        None if with_sub else "서브에이전트 레인 내부",
        "cleanupPeriodDays로 삭제된 기간",
    ] if x],
}
print(json.dumps(out, ensure_ascii=False, indent=2))
