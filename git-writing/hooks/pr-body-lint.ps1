# PostToolUse 훅 — PR·이슈·코멘트를 올린 직후 본문 파일에 git-writing 린트를 돌려 결과를 알린다.
#
# PR·이슈·코멘트 본문의 린트는 에이전트가 스킬을 떠올려 직접 돌려야 한다. 원작성자 실측에서
# PR·이슈를 만든 세션의 8분의 1은 스킬을 로드하지 않았고, 그 본문은 검사 없이 올라갔다.
#  - PostToolUse라서 아무것도 차단하지 못한다. 걸린 문장만 알리고 고치는 것은 edit로 한다.
#    린트는 금지 목록이 아니라 후보 목록이라 막으면 정확한 문장까지 우회하게 된다.
#  - 판별에 실패하면 조용히 통과한다. 훅이 작업을 막으면 안 된다.
#  - create·comment를 본문 파일 없이 실행하면 스킬 절차를 건너뛴 것이므로 그 사실을 알린다.
#    edit는 제목·라벨만 고치는 경우가 있어 본문 파일이 없으면 아무것도 하지 않는다.
#  - 등록: settings.json의 PostToolUse에 matcher "Bash|PowerShell"로 건다(README의 훅 절).

$ErrorActionPreference = 'SilentlyContinue'

# 훅 stdin/stdout은 UTF-8이다. 콘솔 기본 코드페이지(cp949)로 두면 주입 텍스트와 린트 출력이 깨진다.
try {
    [Console]::InputEncoding  = [System.Text.UTF8Encoding]::new($false)
    [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
} catch {}

$raw = [Console]::In.ReadToEnd()
if (-not $raw) { exit 0 }
try { $payload = $raw | ConvertFrom-Json } catch { exit 0 }

$command = $null
foreach ($p in @('tool_input', 'toolInput', 'input')) {
    if ($payload.$p -and $payload.$p.command) { $command = $payload.$p.command; break }
}
if (-not $command) { exit 0 }
# 줄바꿈도 명령 구분자로 본다. -match의 ^는 문자열 전체의 맨 앞에만 맞아서, 빼면 여러 줄 명령의 둘째 줄 이후를 놓친다.
if ($command -notmatch '(?:^|[;&|\r\n]\s*)gh\s+(pr|issue)\s+(create|comment|edit)\b') { exit 0 }
$kind = $Matches[1]
$verb = $Matches[2]
$label = "gh $kind $verb"

# --- 본문 파일: --body-file <경로>, --body-file=<경로>, -F <경로> ------------
# -cmatch로 대소문자를 가른다. -match면 `gh pr create -f`(--fill)를 -F로 읽어 다음 토큰을 파일로 잡는다.
$bodyFile = $null
if ($command -cmatch '(?:^|\s)(?:--body-file|-F)(?:\s+|=)(?:"([^"]+)"|''([^'']+)''|([^\s;&|]+))') {
    $bodyFile = @($Matches[1], $Matches[2], $Matches[3]) | Where-Object { $_ } | Select-Object -First 1
}

if (-not $bodyFile) {
    if ($verb -eq 'edit') { exit 0 }
    if ($verb -eq 'create' -and $command -match '(?:^|\s)(?:--web|-w)\b') { exit 0 }
    $msg = "[본문 린트] $label 명령을 본문 파일 없이 실행했다. git-writing 스킬은 본문을 파일로 쓰고 린트·판정자를 거친 뒤 --body-file로 올린다. 그 절차를 건너뛰었다면 지금 본문을 파일로 옮겨 점검하고, 고칠 것이 있으면 gh $kind edit --body-file(코멘트는 gh $kind comment --edit-last --body-file)로 고친다."
} else {
    if ($bodyFile -eq '-') { exit 0 }

    # 상대 경로는 명령의 작업 디렉터리 기준이다. comprehension-gate.ps1과 같은 순서로 찾는다.
    $cwd = $payload.cwd
    if (-not $cwd) { $cwd = (Get-Location).Path }
    if ($command -match '(?:^|[;&|]\s*)cd\s+"([^"]+)"\s*&&') { $cwd = $Matches[1] }
    elseif ($command -match "(?:^|[;&|]\s*)cd\s+'([^']+)'\s*&&") { $cwd = $Matches[1] }
    elseif ($command -match '(?:^|[;&|]\s*)cd\s+([^\s;&|]+)\s*&&') { $cwd = $Matches[1] }
    # Bash 도구는 `/c/Git/...` 형식을 쓴다. Windows 경로로 바꾼다.
    if ($cwd -match '^/([a-zA-Z])(/.*)?$') { $cwd = $Matches[1] + ':' + $(if ($Matches[2]) { $Matches[2] } else { '/' }) }
    if ($bodyFile -match '^/([a-zA-Z])(/.*)$') { $bodyFile = $Matches[1] + ':' + $Matches[2] }
    if (-not [IO.Path]::IsPathRooted($bodyFile)) { $bodyFile = Join-Path $cwd $bodyFile }
    if (-not (Test-Path -LiteralPath $bodyFile)) { exit 0 }

    # 스킬을 이 경로 밖에 설치했으면(플러그인 등) 실제 prose-lint.py 위치로 고친다. 못 찾으면 린트 없이 끝난다.
    $lint = Join-Path $env:USERPROFILE '.claude\skills\git-writing\scripts\prose-lint.py'
    if (-not (Test-Path -LiteralPath $lint)) { exit 0 }
    $lintOut = & python $lint $bodyFile 2>$null
    if (-not $lintOut) { exit 0 }

    # 걸린 줄(L<번호>:)과 그 줄이 속한 규칙 제목만 남긴다.
    $hits = @()
    $header = $null
    $headerShown = $false
    foreach ($line in $lintOut) {
        if ($line -match '^## ') { $header = $line; $headerShown = $false; continue }
        if ($line -match '^L\d+:') {
            if ($header -and -not $headerShown) { $hits += $header; $headerShown = $true }
            $hits += $line
        }
    }
    if (-not ($hits | Where-Object { $_ -match '^L\d+:' })) { exit 0 }

    $msg = "[본문 린트] $label 명령의 본문 파일($bodyFile)에 git-writing 린트를 돌렸다. 걸린 문장:`n" + ($hits -join "`n") + "`n사실을 정확히 말하는 문장이거나 이미 검토해 남긴 문장이면 그대로 둔다. 고칠 것이 있으면 같은 파일을 고쳐 gh $kind edit --body-file(코멘트는 gh $kind comment --edit-last --body-file)로 다시 올린다."
}

$out = @{
    hookSpecificOutput = @{
        hookEventName     = 'PostToolUse'
        additionalContext = $msg
    }
} | ConvertTo-Json -Depth 5 -Compress

[Console]::Out.Write($out)
exit 0
