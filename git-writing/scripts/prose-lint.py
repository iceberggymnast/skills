#!/usr/bin/env python3
"""git-writing 산문 린트 — PR·이슈·커밋 본문에서 다시 읽어야 할 문장을 찾아 인용한다.

사용:  python prose-lint.py <본문 파일>        (출력을 파일로 남기려면 > lint.txt)
출력:  항목별로 걸린 문장을 줄 번호와 함께 인용한다. 걸린 것이 없으면 "없음".
종료:  항상 0. 이 스크립트는 후보를 찾을 뿐 판정하지 않는다.

설계 원칙:
 - 금지 목록이 아니다. "조용히 넘어갔다"(에러 없이 폴백했다)처럼 사실을 정확히 말하는
   문장은 걸려도 그대로 둔다. 판정은 초안을 쓰지 않은 판정자가 한다(SKILL.md "올리기 전 검사").
 - 세는 단위는 문단(줄)이다. 문서 전체로 세면 검증 체크리스트의 짧은 항목들이 줄줄이
   오탐으로 잡힌다. 문단 단위로 묶으면 그 오탐이 사라지고 서술 구간만 남는다(원작성자 실측).
 - 코드 블록·표·헤더·인용은 세지 않는다. 인라인 코드는 자리표시자로 바꿔 길이만 남긴다.
 - 정규식 근사다. 놓치는 것도 잘못 잡는 것도 있고, 판정자 단계가 그 오차를 흡수한다.
 - 문장 길이는 세지 않는다. 실측 평균이 31~63자라 "25자 이내 셋 연속" 같은 기준은 걸리지
   않았고, 실제로 걸린 것은 연결어미 없는 단정문의 연속이었다.
"""
import io
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# 문장 끝: 합쇼체(-습니다)·해라체(-다) 모두 "다"로 끝난다. 괄호로 닫히는 문장은 세지 않는다(보수적).
END = re.compile(r"다\.?$")
# 연결어미·보조 연결: 이 중 하나라도 있으면 문장 안에서 절이 이어진 것으로 본다.
CONN = re.compile(
    r"(아서|어서|여서|해서|라서|니까|므로|기 때문|이라 |라 "      # 인과
    r"|지만|는데|은데|인데|더라도|어도 |아도 "                     # 역접·양보
    r"|으면 |면 |고,|고 |며 |면서|다가 "                          # 조건·나열·순차
    r"|어 |아 |해 |되 |게 되|게 해)"                              # 보조 연결
)
SENT_SPLIT = re.compile(r"(?<=[다요까죠])[.!?](?=\s|$)|(?<=[.!?])\s+(?=[가-힣A-Z\"“])")

VOCAB = re.compile(r"갈라지|갈라집|갈라진|무너지|무너집|무너진|덮습니다|덮는다|덮습|뺏|밖으로 빼|박힙|박힌다|두 줄기|조용히|삼켜|눕는|눕습|착지")
CONTRAST = re.compile(r"(가|이|은|는|를|을) 아니라|이 아닌 |가 아닌 ")
QUANT = re.compile(r"한두 |대부분|상당 부분|상당히|꽤 |대체로")
ENUM = re.compile(r"(두|세|네|다섯) ?(가지|줄기|축|건|갈래)입니다|크게 (두|세|네) ?(가지|줄기|축)")
FOOTER = re.compile(r"Generated with|^🤖")

BOLD_LEAD_MAX = 30      # 볼드 첫 문장이 이보다 짧은 단정이면 "골격" 후보
BOLD_LEAD_MIN_HITS = 3  # 볼드 단정 오프너는 문서에서 이만큼 반복될 때만 보고한다


def read(path):
    with open(path, encoding="utf-8-sig") as f:
        return f.read()


def paragraphs(text):
    """(줄 번호, 종류, 볼드 시작 여부, 문장 목록)을 낸다. 코드 블록·표·헤더·구분선·인용은 건너뛴다."""
    in_code = False
    for no, raw in enumerate(text.splitlines(), 1):
        s = raw.strip()
        if s.startswith("```"):
            in_code = not in_code
            continue
        if in_code or not s:
            continue
        if s.startswith(("|", "#", "<!--", "---", ">")):
            continue
        bullet = bool(re.match(r"^([-*]|\d+\.)\s+", s))
        s = re.sub(r"^([-*]|\d+\.)\s+", "", s)
        s = re.sub(r"^\[.\]\s+", "", s)
        bold_lead = s.startswith("**")
        s = re.sub(r"`[^`]*`", "C", s)
        s = s.replace("**", "")
        sents = [p.strip() for p in SENT_SPLIT.split(s) if p and len(p.strip()) > 3]
        if sents:
            yield no, ("bullet" if bullet else "prose"), bold_lead, sents


def is_flat(sent):
    """연결어미 없이 단정으로 끝나는 문장인가."""
    return bool(END.search(sent)) and not CONN.search(sent)


def clip(s, n=70):
    return s if len(s) <= n else s[: n - 1] + "…"


def main(path):
    text = read(path)
    paras = list(paragraphs(text))
    findings = {}

    # 1. 문단 안에서 연결어미 없는 단정문이 셋 이상 연속
    runs = []
    for no, kind, _, sents in paras:
        k = 0
        for i, s in enumerate(sents):
            k = k + 1 if is_flat(s) else 0
            if k == 3:
                runs.append((no, " / ".join(clip(x, 40) for x in sents[i - 2 : i + 1])))
    findings["1. 문단 안에서 단정문 셋 연속 — 인과·역접이면 연결어미로 잇고, 나열이면 불릿으로 내린다"] = runs

    # 2. 볼드 단정문으로 시작하는 문단이 반복
    bold = [
        (no, clip(sents[0]))
        for no, kind, bold_lead, sents in paras
        if kind == "prose" and bold_lead and len(sents) >= 2 and len(sents[0]) <= BOLD_LEAD_MAX and END.search(sents[0])
    ]
    findings[f"2. 볼드 단정문으로 여는 문단 {BOLD_LEAD_MIN_HITS}곳 이상 — 같은 모양이 반복되면 골격이 티 난다. 일부는 평문으로 시작한다"] = (
        bold if len(bold) >= BOLD_LEAD_MIN_HITS else []
    )

    # 3. 열거 오프너
    findings["3. \"두 가지입니다\"·\"크게 두 줄기입니다\" 식 열거 오프너 — 첫 항목을 바로 쓴다"] = [
        (no, clip(s)) for no, _, _, sents in paras for s in sents if ENUM.search(s)
    ]

    # 4. 비유·극적 동사 후보
    findings["4. 비유·극적 동사 후보 — 그 자리에 들어갈 실측·호출 순서를 찾아 넣는다. 사실을 정확히 말하는 문장이면 그대로 둔다"] = [
        (no, clip(s)) for no, _, _, sents in paras for s in sents if VOCAB.search(s)
    ]

    # 5. 대구
    findings["5. \"A가 아니라 B\" 대조 구문 — 3곳 이상이면 반복이다. 일부는 B만 쓴다"] = [
        (no, clip(s)) for no, _, _, sents in paras for s in sents if CONTRAST.search(s)
    ]

    # 6. 근거 없는 수량 표현
    findings["6. 수량 표현(한두·대부분·상당 부분·꽤) — 세어서 숫자로 바꿀 수 있으면 바꾼다"] = [
        (no, clip(s)) for no, _, _, sents in paras for s in sents if QUANT.search(s)
    ]

    # 7. 도구 푸터
    findings["7. 도구가 붙인 자동 푸터 — 지운다"] = [
        (no, clip(line.strip())) for no, line in enumerate(text.splitlines(), 1) if FOOTER.search(line.strip())
    ]

    total = 0
    print(f"# prose-lint: {path}")
    for title, items in findings.items():
        print(f"\n## {title}")
        if not items:
            print("없음")
            continue
        total += len(items)
        for no, s in items:
            print(f"L{no}: {s}")
    print(f"\n합계 {total}건")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("사용: python prose-lint.py <본문 파일>")
        sys.exit(2)
    main(sys.argv[1])
