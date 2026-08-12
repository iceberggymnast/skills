# skills

Claude Code에서 쓰는 개인 제작 스킬 모음입니다.

| 스킬 | 하는 일 |
|---|---|
| [git-writing](git-writing/SKILL.md) | 팀원이 읽는 git 텍스트(PR 본문·이슈·커밋 메시지)를 사람이 한 번에 읽히게 쓴다. AI 특유의 고밀도 문장·설명 없는 내부 용어·어미 섞임을 고치는 문장 규칙 모음 |
| [pr-review-loop](pr-review-loop/SKILL.md) | 팀원이 올린 PR을 리뷰한다. 충돌 확인 → 설계 문서 대조 → 코드 리뷰 → 이해도 대조 → 에디터에서 사람이 직접 확인할 항목을 O/X 체크리스트로 분리 생성 → 머지까지 한 절차로 |
| [senior-mentor](senior-mentor/SKILL.md) | 고쳐주는 봇이 아니라 물어보는 사수. AI가 짠 코드를 사용자가 설명할 수 있는지(이해 부채)를 예측–대조로 재고, 모르면 가르친다 |

## 설치

폴더째 `~/.claude/skills/` 아래에 복사하면 됩니다.

```
~/.claude/skills/
├── git-writing/
├── pr-review-loop/
└── senior-mentor/
```

## 처음 받았다면

**`senior-mentor`와 `pr-review-loop`는 세트입니다.** 이해 부채 원장(`comprehension-debt.md`)과 도입 절차를 공유하고, 한쪽이 적재한 기록을 다른 쪽이 소비하도록 설계되어 있어 같이 가져가야 합니다. 하나만 받으면 지표의 절반이 빕니다.

두 스킬은 사용자 프로필(`mentee-profile.md`)과 관측 기록(`RATIONALE.md`)을 전제로 동작합니다. 두 파일은 원작성자의 개인 기록이라 배포에 포함되지 않으며, [senior-mentor/BOOTSTRAP.md](senior-mentor/BOOTSTRAP.md)의 절차를 따라 자기 것을 만들면 됩니다. `git-writing`의 `RATIONALE.md`도 같은 방식으로 각자 만듭니다.

커밋·PR 직후 자동 발동에 쓰는 훅(`senior-mentor/hooks/comprehension-gate.ps1`)도 포함되어 있습니다. 세팅 절차는 BOOTSTRAP.md 3단계에 있습니다.

## 라이선스

MIT
