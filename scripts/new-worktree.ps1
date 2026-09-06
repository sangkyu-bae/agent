<#
.SYNOPSIS
    병렬 PDCA 작업용 git worktree를 생성하고 개발 환경을 셋업한다.

.DESCRIPTION
    feature 하나 = worktree 하나 = Claude Code 세션 하나 원칙을 지키기 위한 스크립트.
    worktree 생성 → 백엔드 의존성(uv sync) → 프론트 node_modules junction →
    .env 복사 및 포트 분리까지 한 번에 처리한다.

    상세 규칙: .claude/skills/git-workflow/SKILL.md 의 "0. 작업 공간 준비" 참조.

.PARAMETER Name
    작업 공간 폴더명. ../wt/<Name> 에 생성된다.

.PARAMETER Branch
    생성할 브랜치명. 생략하면 "feature/<Name>".

.PARAMETER Base
    기점 브랜치. 생략하면 origin/HEAD 에서 자동 감지한다.

.PARAMETER ExistingBranch
    이미 존재하는 브랜치에 worktree를 붙인다 (새 브랜치를 만들지 않음).

.PARAMETER NoFront
    프론트엔드(idt_front) 셋업을 건너뛴다.

.PARAMETER SkipSync
    백엔드 uv sync 를 건너뛴다.

.PARAMETER DryRun
    실제로 실행하지 않고 수행할 작업만 출력한다.

.EXAMPLE
    .\scripts\new-worktree.ps1 -Name agent-webhook

.EXAMPLE
    .\scripts\new-worktree.ps1 -Name kb-filter -Branch fix/kb-filter -NoFront

.EXAMPLE
    .\scripts\new-worktree.ps1 -Name eval-hub -ExistingBranch -Branch feature/eval-hub
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidatePattern('^[A-Za-z0-9._-]+$')]
    [string]$Name,

    [string]$Branch,
    [string]$Base,
    [switch]$ExistingBranch,
    [switch]$NoFront,
    [switch]$SkipSync,
    [switch]$DryRun,

    # 설치할 optional-dependencies extra 목록.
    # 기본 'dev' = pytest / ruff / mypy. 이게 없으면 worktree에서 테스트를 못 돌린다.
    # ⚠️ 'eval' 은 기본에서 제외한다 — ragas 0.4.x 가 openai<3 을 요구해
    #    현재 고정된 openai 3.x 를 메이저 다운그레이드시킨다 (pyproject.toml 주석 참조).
    [string[]]$Extras = @('dev')
)

$ErrorActionPreference = 'Stop'

# ── 출력 헬퍼 ────────────────────────────────────────────────
$script:stepNo = 0
function Write-Step([string]$msg) {
    $script:stepNo++
    Write-Host ""
    Write-Host ("[{0}] {1}" -f $script:stepNo, $msg) -ForegroundColor Cyan
}
function Write-Ok([string]$msg) {
    $prefix = ''
    if ($DryRun) { $prefix = '[dry-run] ' }
    Write-Host "    OK   $prefix$msg" -ForegroundColor Green
}
function Write-Skip([string]$msg) { Write-Host "    SKIP $msg" -ForegroundColor DarkGray }
function Write-Warn2([string]$msg){ Write-Host "    WARN $msg" -ForegroundColor Yellow }

function Invoke-Git {
    param([string[]]$GitArgs, [string]$WorkDir)
    if (-not $WorkDir) { $WorkDir = $script:RepoRoot }
    if ($DryRun) {
        Write-Host ("    [dry-run] git -C {0} {1}" -f $WorkDir, ($GitArgs -join ' ')) -ForegroundColor DarkYellow
        return ""
    }
    # PS 5.1 주의: ErrorActionPreference='Stop' 상태에서 네이티브 stderr 를 2>&1 로
    # 받으면 NativeCommandError 로 감싸져 throw 된다. git 은 진행률을 stderr 로 쓰므로
    # 정상 동작마저 예외가 된다. 여기서만 Continue 로 낮춰 문자열로 수집한다.
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $out = & git -C $WorkDir @GitArgs 2>&1 | ForEach-Object { $_.ToString() }
    } finally {
        $ErrorActionPreference = $prevEap
    }
    if ($LASTEXITCODE -ne 0) {
        throw ("git {0} 실패 (exit {1}):`n{2}" -f ($GitArgs -join ' '), $LASTEXITCODE, ($out -join "`n"))
    }
    return ($out -join "`n")
}

# ── 1. 리포지토리 루트 확인 ──────────────────────────────────
Write-Step "리포지토리 확인"

$topLevel = & git rev-parse --show-toplevel 2>$null
if ($LASTEXITCODE -ne 0) { throw "git 리포지토리가 아닙니다. 저장소 안에서 실행하세요." }
$script:RepoRoot = (Resolve-Path ($topLevel.Trim())).Path

# worktree 안에서 실행한 경우 메인 워킹트리를 기준으로 삼는다
$commonDir = (& git -C $RepoRoot rev-parse --path-format=absolute --git-common-dir 2>$null)
if ($LASTEXITCODE -eq 0 -and $commonDir) {
    $mainRoot = Split-Path -Parent ($commonDir.Trim())
    if ((Test-Path $mainRoot) -and ($mainRoot -ne $RepoRoot)) {
        Write-Warn2 "worktree 안에서 실행됨 → 메인 워킹트리 기준으로 진행합니다"
        $script:RepoRoot = (Resolve-Path $mainRoot).Path
    }
}
Write-Ok "repo root: $RepoRoot"

# ── 2. 기본 브랜치 감지 ──────────────────────────────────────
Write-Step "기본 브랜치 감지"

if (-not $Base) {
    $head = & git -C $RepoRoot symbolic-ref --short refs/remotes/origin/HEAD 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $head) {
        Write-Warn2 "origin/HEAD 미설정 → git remote set-head origin -a 로 복구 시도"
        & git -C $RepoRoot remote set-head origin -a | Out-Null
        $head = & git -C $RepoRoot symbolic-ref --short refs/remotes/origin/HEAD 2>$null
    }
    if ($LASTEXITCODE -ne 0 -or -not $head) {
        throw "기본 브랜치를 감지하지 못했습니다. -Base 로 직접 지정하세요."
    }
    $Base = $head.Trim() -replace '^origin/', ''
}
Write-Ok "base: $Base"

if (-not $Branch) { $Branch = "feature/$Name" }
Write-Ok "branch: $Branch"

# ── 3. 대상 경로 확인 ────────────────────────────────────────
Write-Step "대상 경로 확인"

$WtRoot = Join-Path (Split-Path -Parent $RepoRoot) 'wt'
$Target = Join-Path $WtRoot $Name

if (Test-Path $Target) {
    throw "이미 존재합니다: $Target`n다른 -Name 을 쓰거나, 기존 작업 공간에서 세션을 여세요."
}

$wtList = & git -C $RepoRoot worktree list --porcelain 2>$null
if ($wtList -match [regex]::Escape("branch refs/heads/$Branch")) {
    throw "브랜치 '$Branch' 는 이미 다른 worktree가 사용 중입니다.`n확인: git worktree list"
}

$branchExists = $false
& git -C $RepoRoot show-ref --verify --quiet "refs/heads/$Branch"
if ($LASTEXITCODE -eq 0) { $branchExists = $true }

if ($branchExists -and -not $ExistingBranch) {
    throw "브랜치 '$Branch' 가 이미 존재합니다.`n이어서 작업하려면 -ExistingBranch 를 붙이세요."
}
if ($ExistingBranch -and -not $branchExists) {
    throw "-ExistingBranch 를 줬지만 '$Branch' 브랜치가 없습니다."
}

if (-not $DryRun) { New-Item -ItemType Directory -Path $WtRoot -Force | Out-Null }
Write-Ok "target: $Target"

# ── 4. 포트 배정 (기존 worktree와 겹치지 않게) ───────────────
Write-Step "포트 배정"

$usedApi = New-Object System.Collections.Generic.List[int]
$usedWeb = New-Object System.Collections.Generic.List[int]
$usedApi.Add(8000) | Out-Null      # 메인 폴더가 쓰는 기본 포트
$usedWeb.Add(5173) | Out-Null

# (a) 다른 worktree 가 이미 배정받은 포트
if (Test-Path $WtRoot) {
    Get-ChildItem -Path $WtRoot -Directory -ErrorAction SilentlyContinue | ForEach-Object {
        $envFile = Join-Path $_.FullName 'idt_front\.env.local'
        if (Test-Path $envFile) {
            $hit = Select-String -Path $envFile -Pattern 'VITE_API_BASE_URL=http://localhost:(\d+)' -ErrorAction SilentlyContinue
            if ($hit) { $usedApi.Add([int]$hit.Matches[0].Groups[1].Value) | Out-Null }
        }
    }
}

# (b) 실제로 LISTEN 중인 포트.
#     이 프로젝트는 MCP 서버 컨테이너가 8001~8003 을 이미 점유하고 있으므로
#     .env 스캔만으로는 충돌을 못 잡는다. 반드시 실측해야 한다.
$listening = @()
try {
    $listening = @(Get-NetTCPConnection -State Listen -ErrorAction Stop | Select-Object -ExpandProperty LocalPort -Unique)
} catch {
    # Get-NetTCPConnection 이 없는 환경(구형 Windows 등) 대비
    $listening = @(netstat -an | Select-String -Pattern '^\s+TCP\s+\S+:(\d+)\s+\S+\s+LISTENING' |
                   ForEach-Object { [int]$_.Matches[0].Groups[1].Value } | Sort-Object -Unique)
}
foreach ($p in $listening) {
    if (-not $usedApi.Contains([int]$p)) { $usedApi.Add([int]$p) | Out-Null }
    if (-not $usedWeb.Contains([int]$p)) { $usedWeb.Add([int]$p) | Out-Null }
}

$ApiPort = 8001
while ($usedApi -contains $ApiPort) { $ApiPort++ }
$WebPort = 5174
while (($usedWeb -contains $WebPort) -or ($WebPort -eq $ApiPort)) { $WebPort++ }

$busy = @($listening | Where-Object { $_ -ge 8000 -and $_ -lt 8010 }) -join ', '
Write-Ok "API $ApiPort / WEB $WebPort"
if ($busy) { Write-Warn2 "8000번대 사용 중: $busy (MCP 서버 컨테이너 등) → 피해서 배정함" }

# ── 5. worktree 생성 ─────────────────────────────────────────
Write-Step "worktree 생성"

Invoke-Git @('fetch', 'origin', $Base) | Out-Null
Write-Ok "fetch origin/$Base"

if ($ExistingBranch) {
    Invoke-Git @('worktree', 'add', $Target, $Branch) | Out-Null
    Write-Ok "기존 브랜치 '$Branch' 에 연결"
} else {
    Invoke-Git @('worktree', 'add', $Target, '-b', $Branch, "origin/$Base") | Out-Null
    Write-Ok "새 브랜치 '$Branch' 생성 (기점: origin/$Base)"
}

# ── 6. .env 복사 ─────────────────────────────────────────────
Write-Step ".env 복사"

# BOM 없는 UTF-8 로 기록 (dotenv 파서가 BOM을 키 이름에 포함시키는 문제 방지)
function Write-TextNoBom([string]$Path, [string]$Text) {
    $enc = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Text, $enc)
}

$backendEnvSrc = Join-Path $RepoRoot 'idt\.env'
$backendEnvDst = Join-Path $Target   'idt\.env'
if (Test-Path $backendEnvSrc) {
    if (-not $DryRun) { Copy-Item $backendEnvSrc $backendEnvDst -Force }
    Write-Ok "idt/.env 복사 (DB/Qdrant 는 메인과 공유됨 — 마이그레이션 주의)"
} else {
    Write-Warn2 "idt/.env 없음 → idt/.env.example 을 참고해 직접 만드세요"
}

if (-not $NoFront) {
    $frontEnvSrc = Join-Path $RepoRoot 'idt_front\.env.local'
    $frontEnvDst = Join-Path $Target   'idt_front\.env.local'
    if (Test-Path $frontEnvSrc) {
        if (-not $DryRun) {
            $text = Get-Content $frontEnvSrc -Raw -Encoding UTF8
            $text = $text -replace 'VITE_API_BASE_URL=http://localhost:\d+', "VITE_API_BASE_URL=http://localhost:$ApiPort"
            $text = $text -replace 'VITE_WS_URL=ws://localhost:\d+',        "VITE_WS_URL=ws://localhost:$ApiPort"
            Write-TextNoBom $frontEnvDst $text
        }
        Write-Ok "idt_front/.env.local 복사 + API 포트를 $ApiPort 로 변경"
    } else {
        Write-Warn2 "idt_front/.env.local 없음 → .env.local.example 참고"
    }
}

# ── 7. 백엔드 의존성 ─────────────────────────────────────────
Write-Step "백엔드 의존성 (uv sync)"

$syncArgs = @('sync')
foreach ($e in $Extras) { $syncArgs += @('--extra', $e) }

if ($SkipSync) {
    Write-Skip "-SkipSync 지정됨"
} elseif ($DryRun) {
    Write-Host ("    [dry-run] uv {0}  (in {1}\idt)" -f ($syncArgs -join ' '), $Target) -ForegroundColor DarkYellow
} elseif (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Warn2 ("uv 를 찾을 수 없습니다 → 새 폴더에서 직접 'uv {0}' 실행하세요" -f ($syncArgs -join ' '))
} else {
    Push-Location (Join-Path $Target 'idt')
    try {
        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        & uv @syncArgs
        $sw.Stop()
        if ($LASTEXITCODE -ne 0) {
            Write-Warn2 "uv sync 실패 (exit $LASTEXITCODE) → 새 폴더에서 수동 실행 필요"
        } else {
            Write-Ok ("uv {0} 완료 ({1:N1}초)" -f ($syncArgs -join ' '), $sw.Elapsed.TotalSeconds)
        }
    } finally { Pop-Location }
}

# ── 8. 프론트 node_modules junction ──────────────────────────
Write-Step "프론트 node_modules junction"

if ($NoFront) {
    Write-Skip "-NoFront 지정됨"
} else {
    $nmSrc = Join-Path $RepoRoot 'idt_front\node_modules'
    $nmDst = Join-Path $Target   'idt_front\node_modules'
    if (-not (Test-Path $nmSrc)) {
        Write-Warn2 "메인 node_modules 없음 → 새 폴더에서 'npm ci' 실행 필요"
    } elseif ($DryRun) {
        Write-Host "    [dry-run] Junction $nmDst -> $nmSrc" -ForegroundColor DarkYellow
    } else {
        New-Item -ItemType Junction -Path $nmDst -Target $nmSrc | Out-Null
        Write-Ok "junction 생성 (메인 node_modules 공유)"
        Write-Warn2 "package-lock.json 을 바꿀 예정이면 junction 제거 후 'npm ci' 하세요"
        Write-Warn2 "  제거: [System.IO.Directory]::Delete('$nmDst', `$false)"
    }
}

# ── 9. 요약 ──────────────────────────────────────────────────
Write-Host ""
Write-Host "════════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host " 작업 공간 준비 완료" -ForegroundColor Green
Write-Host "════════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host ""
Write-Host "  경로     : $Target"
Write-Host "  브랜치   : $Branch  (기점: origin/$Base)"
Write-Host "  API 포트 : $ApiPort"
Write-Host "  WEB 포트 : $WebPort"
Write-Host ""
Write-Host "  다음 단계:" -ForegroundColor Cyan
Write-Host "    1) 새 터미널에서 해당 폴더를 열고 Claude Code 세션 시작"
Write-Host "         cd `"$Target`""
Write-Host "    2) 서버 실행 (포트를 반드시 지정할 것)"
Write-Host "         cd idt        ; uvicorn src.main:app --reload --port $ApiPort"
Write-Host "         cd idt_front  ; npm run dev -- --port $WebPort"
Write-Host ""
Write-Host "  머지 후 정리 (순서 중요):" -ForegroundColor Cyan
Write-Host "     1) junction 부터 제거 — 링크를 남긴 채 폴더를 지우면" -ForegroundColor Yellow
Write-Host "        메인 node_modules 까지 삭제될 수 있습니다" -ForegroundColor Yellow
Write-Host "         [System.IO.Directory]::Delete('$Target\idt_front\node_modules', `$false)"
Write-Host "     2) worktree 제거"
Write-Host "         git -C `"$RepoRoot`" worktree remove `"$Target`""
Write-Host "         git -C `"$RepoRoot`" branch -d $Branch"
Write-Host ""
Write-Host "  주의: MySQL/Qdrant 는 메인과 공유됩니다." -ForegroundColor Yellow
Write-Host "        db/migration 번호 선점과 컬렉션 충돌에 유의하세요." -ForegroundColor Yellow
Write-Host ""

# show-ref 등 read-only git 호출이 남긴 $LASTEXITCODE 가 스크립트 종료 코드로
# 새는 것을 막는다 (여기까지 왔으면 성공).
exit 0
