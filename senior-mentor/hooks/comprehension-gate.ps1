# PostToolUse 훅 — 커밋/PR 직후 이해 확인(senior-mentor)을 발동시킨다.
#
# 설계 원칙:
#  - PostToolUse라서 구조적으로 아무것도 차단하지 못한다. 알림만 한다.
#  - 입력 형식을 못 읽거나 판별에 실패하면 조용히 통과한다. 훅이 작업을 막으면 안 된다.
#  - 대상 판정: 확장자 화이트리스트 AND NOT 경로 블랙리스트

$ErrorActionPreference = 'SilentlyContinue'

# Claude Code는 훅 stdin/stdout을 UTF-8로 다룬다. 콘솔 기본 코드페이지(cp949 등)로 두면
#   주입 텍스트의 비ASCII 문자가 깨지므로 입출력 인코딩을 UTF-8로 고정한다.
try {
    [Console]::InputEncoding  = [System.Text.UTF8Encoding]::new($false)
    [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
} catch {}

function Write-Probe($text) {
    if ($env:COMPREHENSION_GATE_DEBUG -eq '1') {
        Add-Content -Path (Join-Path $PSScriptRoot 'probe.log') -Value $text -Encoding UTF8
    }
}

$raw = [Console]::In.ReadToEnd()
Write-Probe ("=== {0} ===`n{1}`n" -f (Get-Date -Format 'o'), $raw)
if (-not $raw) { exit 0 }

try { $payload = $raw | ConvertFrom-Json } catch { exit 0 }

# 실행된 명령 문자열 추출. 키 이름이 다를 수 있으므로 후보를 순회한다.
$command = $null
foreach ($p in @('tool_input', 'toolInput', 'input')) {
    if ($payload.$p -and $payload.$p.command) { $command = $payload.$p.command; break }
}
if (-not $command) { exit 0 }

# --- 어떤 종류의 이벤트인가 -------------------------------------------------
# git commit  → 디테일 확인(예측-대조)
# gh pr create → 러프 복습(커밋에 쌓인 부채 기록 재확인)
$isCommit = $command -match '(^|[;&|]\s*)git\s+(-C\s+\S+\s+|--\S+\s+)*commit\b'
$isPr     = $command -match '(^|[;&|]\s*)gh\s+pr\s+create\b'
if (-not ($isCommit -or $isPr)) { exit 0 }

# amend / --no-edit 재작성은 새 변경이 아니므로 건너뛴다
if ($isCommit -and $command -match '--amend') { exit 0 }

# --- 작업 디렉터리 ----------------------------------------------------------
$cwd = $payload.cwd
if (-not $cwd) { foreach ($p in @('tool_input','toolInput','input')) { if ($payload.$p.cwd) { $cwd = $payload.$p.cwd; break } } }
if (-not $cwd) { $cwd = (Get-Location).Path }

# 명령에 -C <경로>가 있으면 그쪽을 우선한다
if ($command -match 'git\s+-C\s+"([^"]+)"') { $cwd = $Matches[1] }
elseif ($command -match "git\s+-C\s+'([^']+)'") { $cwd = $Matches[1] }
elseif ($command -match 'git\s+-C\s+(\S+)') { $cwd = $Matches[1] }
# `cd <경로> && git commit` 형태도 잡는다. -C가 없으면 세션 cwd가 남아
#   엉뚱한 레포의 HEAD를 읽는다 (실측 오탐: 문서 레포 커밋인데 다른 레포의 HEAD를 봤다).
elseif ($command -match '(?:^|[;&|]\s*)cd\s+"([^"]+)"\s*&&') { $cwd = $Matches[1] }
elseif ($command -match "(?:^|[;&|]\s*)cd\s+'([^']+)'\s*&&") { $cwd = $Matches[1] }
elseif ($command -match '(?:^|[;&|]\s*)cd\s+([^\s;&|]+)\s*&&') { $cwd = $Matches[1] }

# 판정 대상 레포를 확정한다. 위 추출이 하위 디렉터리를 가리켜도 실제 저장소 루트로 정규화한다.
$repoRoot = & git -C "$cwd" rev-parse --show-toplevel 2>$null
if ($repoRoot) { $cwd = $repoRoot }

# --- 방금 커밋된 파일 목록 --------------------------------------------------
# --name-status로 받아 삭제(D)를 걸러낸다. 지워진 파일로 예측 질문을 만들면
#   측정이 아니라 창작이 된다 (실측 오탐이 정확히 롤백 커밋을 물었다).
if ($isCommit) {
    $rows = & git -C "$cwd" show --pretty=format: --name-status HEAD 2>$null
} else {
    $base = & git -C "$cwd" rev-parse --abbrev-ref origin/HEAD 2>$null
    if (-not $base) { $base = 'origin/main' }
    $rows = & git -C "$cwd" diff --name-status "$base...HEAD" 2>$null
}
if (-not $rows) { exit 0 }

$files = @()
foreach ($row in ($rows | Where-Object { $_ })) {
    $parts = $row -split "`t"
    if ($parts.Count -lt 2) { continue }
    if ($parts[0].StartsWith('D')) { continue }
    # 이름 변경(R100 old new)은 마지막 칸이 새 경로다
    $files += $parts[-1]
}
if ($files.Count -eq 0) { exit 0 }

# --- 대상 판정 --------------------------------------------------------------
$codeExt = @('.h','.hpp','.c','.cpp','.cs','.py','.pyp','.ts','.tsx','.js','.jsx','.css','.scss','.html','.sql','.sh','.ps1')
# 블랙리스트: 코드 확장자가 있어도 이해 확인 대상이 아닌 경로.
# 아래 두 줄 중 첫 줄은 본인 환경에 맞게 채운다 — 문서 레포·노트 볼트·비개발 워크스페이스 등.
$denyPat = @(
    # '내-문서-레포', '내-노트-볼트',
    '[\\/]\.claude[\\/]',
    'node_modules', 'Intermediate', 'Binaries', 'Saved', 'DerivedDataCache', '\.venv'
)

$targets = @()
foreach ($f in ($files | Where-Object { $_ })) {
    $full = Join-Path $cwd $f
    if ([IO.Path]::GetExtension($f).ToLower() -notin $codeExt) { continue }
    $blocked = $false
    foreach ($d in $denyPat) { if ($full -match $d) { $blocked = $true; break } }
    if (-not $blocked) { $targets += $f }
}
if ($targets.Count -eq 0) { exit 0 }

# --- 컨텍스트 주입 ----------------------------------------------------------
$shown = ($targets | Select-Object -First 6) -join ', '
$more  = if ($targets.Count -gt 6) { " 외 $($targets.Count - 6)개" } else { '' }

if ($isCommit) {
    $msg = @"
[이해 확인 대상] 방금 커밋된 코드 파일: $shown$more

senior-mentor 스킬을 모드 C(확인)로 실행하라. 규칙:
- 예측 질문 최대 3개, 파일 최대 2개
- "모르겠다"가 2회 나오면 중단하지 말고 설명 모드로 전환해 가르치고 comprehension-debt.md에 적재
- 커밋은 이미 완료됐다. 되돌리라고 제안하지 마라
- 사용자가 생략을 원하면 따르되 comprehension-debt.md에 스킵 기록 한 줄을 남겨라
"@
} else {
    $msg = @"
[복습 대상] PR에 포함된 코드 파일: $shown$more

senior-mentor 스킬을 러프 복습 모드로 실행하라. 규칙:
- 새 예측 질문을 내지 말고, comprehension-debt.md에서 이 PR 범위에 해당하는 미복습 항목을 꺼내 확인하라
- 확인된 항목은 복습 체크 칸을 채워라
- PR 본문은 Claude가 대신 쓰지 말고 사용자의 답으로 구성하라
"@
}

$out = @{
    hookSpecificOutput = @{
        hookEventName     = 'PostToolUse'
        additionalContext = $msg
    }
} | ConvertTo-Json -Depth 5 -Compress

[Console]::Out.Write($out)
exit 0
