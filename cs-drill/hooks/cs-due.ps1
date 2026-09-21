# SessionStart 훅 — CS 복습 기한이 지난 항목이 있거나 새 항목을 오래 안 열었으면 개수·일수만 알린다(cs-drill).
#
# 설계 원칙:
#  - 개수만 알린다. 개념명을 알리면 사용자가 노트를 먼저 읽고 답할 수 있어 재대조가 무효가 된다.
#  - 아무것도 시작하지 않는다. 훅은 신호만 보내고 실행은 스킬이 한다.
#  - 읽기 실패·형식 불일치는 조용히 통과한다. 훅이 세션을 막으면 안 된다.
#  - 일정의 출처는 진도표 한 곳이다. 표 행만 세지 않으면 학습 항목 본문에 남은
#    같은 표기까지 세어져 한 개념이 두 건으로 보고된다.
#  - 새 항목 신호는 학습 항목 헤딩(### YYYY-MM-DD)의 최신 날짜로 잰다. 기준 14일은
#    복습 간격 표의 최장 간격(1회차 통과 후 +14일)이다. 복습 경로만 돌고 커리큘럼이
#    한 달간 전진하지 않은 것이 관측돼 넣었다. 이 신호가 새 항목 없이 여러 세션 연속
#    울리면 그것이 마찰 신호이고, skill-checkup이 그 횟수를 센다.
#  - 마커 [CS 복습]은 메시지에 한 번만 쓴다. 계기(skill-usage.py)가 이 문구로 발동을 센다.

$ErrorActionPreference = 'SilentlyContinue'
$newItemGapDays = 14

try {
    [Console]::InputEncoding  = [System.Text.UTF8Encoding]::new($false)
    [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
} catch {}

# stdin은 읽고 버린다. 이 훅은 입력 내용을 쓰지 않는다.
try { [Console]::In.ReadToEnd() | Out-Null } catch {}

$ledger = Join-Path $env:USERPROFILE '.claude\cs-progress.md'
if (-not (Test-Path $ledger)) { exit 0 }

try {
    $lines = [IO.File]::ReadAllLines($ledger, [Text.UTF8Encoding]::new($false))
} catch { exit 0 }

$today = (Get-Date).Date
$overdue = 0
$lastNew = $null

foreach ($line in $lines) {
    $t = $line.TrimStart()
    # 표 행만 센다. 진도표가 일정의 유일한 출처이고, 학습 항목 본문에 재대조
    # 기록을 적으며 같은 표기를 남기면 한 개념이 두 번 세어진다.
    if ($t.StartsWith('|')) {
        foreach ($m in [regex]::Matches($line, 'due:(\d{4})-(\d{2})-(\d{2})')) {
            try {
                $d = Get-Date -Year ([int]$m.Groups[1].Value) -Month ([int]$m.Groups[2].Value) -Day ([int]$m.Groups[3].Value)
                if ($d.Date -le $today) { $overdue++ }
            } catch { }
        }
        continue
    }
    # 학습 항목 헤딩의 최신 날짜 = 마지막으로 새 항목을 연 날.
    $h = [regex]::Match($t, '^### (\d{4})-(\d{2})-(\d{2}) ')
    if ($h.Success) {
        try {
            $d = Get-Date -Year ([int]$h.Groups[1].Value) -Month ([int]$h.Groups[2].Value) -Day ([int]$h.Groups[3].Value)
            if ($null -eq $lastNew -or $d.Date -gt $lastNew) { $lastNew = $d.Date }
        } catch { }
    }
}

$stale = 0
if ($null -ne $lastNew) {
    $stale = [int](($today - $lastNew).TotalDays)
    if ($stale -lt $newItemGapDays) { $stale = 0 }
}

if ($overdue -lt 1 -and $stale -lt 1) { exit 0 }

if ($overdue -ge 1 -and $stale -ge 1) {
    $head = "[CS 복습] 기한이 지난 항목 $($overdue)건이 있고, 마지막 새 항목이 $($stale)일 전입니다($($newItemGapDays)일 기준 초과)."
} elseif ($overdue -ge 1) {
    $head = "[CS 복습] 기한이 지난 항목 $($overdue)건이 있습니다."
} else {
    $head = "[CS 복습] 기한이 지난 항목은 없고, 마지막 새 항목이 $($stale)일 전입니다($($newItemGapDays)일 기준 초과)."
}

$msg = @"
$head

cs-drill 스킬의 규칙을 따르되, 지금 바로 문제를 내지 마라:
- 먼저 지금 볼지 한 줄로 묻는다. 작업 중이면 흐름을 끊는 쪽이 손해가 크다
- 하겠다고 하면 한 번에 하나만 낸다. 개념명은 묻기 전에 밝히지 않는다
- 기한 초과 건은 재대조다. 새 항목 신호는 고르는 순서 2·3으로 미착수 항목 하나를 골라 설명 모드로 시작한다 — 재대조가 아니다
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
