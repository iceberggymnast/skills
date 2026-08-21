# SessionStart 훅 — CS 복습 기한이 지난 항목이 있으면 개수만 알린다(cs-drill).
#
# 설계 원칙:
#  - 개수만 알린다. 개념명을 알리면 사용자가 노트를 먼저 읽고 답할 수 있어 재대조가 무효가 된다.
#  - 아무것도 시작하지 않는다. 훅은 신호만 보내고 실행은 스킬이 한다.
#  - 읽기 실패·형식 불일치는 조용히 통과한다. 훅이 세션을 막으면 안 된다.

$ErrorActionPreference = 'SilentlyContinue'

try {
    [Console]::InputEncoding  = [System.Text.UTF8Encoding]::new($false)
    [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
} catch {}

# stdin은 읽고 버린다. 이 훅은 입력 내용을 쓰지 않는다.
try { [Console]::In.ReadToEnd() | Out-Null } catch {}

$ledger = Join-Path $env:USERPROFILE '.claude\cs-progress.md'
if (-not (Test-Path $ledger)) { exit 0 }

try {
    $text = [IO.File]::ReadAllText($ledger, [Text.UTF8Encoding]::new($false))
} catch { exit 0 }

$today = (Get-Date).Date
$overdue = 0

foreach ($m in [regex]::Matches($text, 'due:(\d{4})-(\d{2})-(\d{2})')) {
    try {
        $d = Get-Date -Year ([int]$m.Groups[1].Value) -Month ([int]$m.Groups[2].Value) -Day ([int]$m.Groups[3].Value)
        if ($d.Date -le $today) { $overdue++ }
    } catch { }
}

if ($overdue -lt 1) { exit 0 }

$msg = @"
[CS 복습] 기한이 지난 항목 $overdue 건이 있습니다.

cs-drill 스킬의 규칙을 따르되, 지금 바로 문제를 내지 마라:
- 먼저 지금 볼지 한 줄로 묻는다. 작업 중이면 흐름을 끊는 쪽이 손해가 크다
- 하겠다고 하면 한 번에 하나만 낸다. 개념명은 묻기 전에 밝히지 않는다
- 아니라고 하면 cs-progress.md의 스킵 기록에 한 줄 남기고 끝낸다
"@

$out = @{
    hookSpecificOutput = @{
        hookEventName     = 'SessionStart'
        additionalContext = $msg
    }
} | ConvertTo-Json -Depth 5 -Compress

[Console]::Out.Write($out)
exit 0
