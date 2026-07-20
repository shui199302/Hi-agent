[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Continue"

$RootDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ToolsDir = Join-Path $RootDir ".tools"
$BinDir = Join-Path $ToolsDir "bin"
$NodeDir = Join-Path $ToolsDir "node"
$env:UV_CACHE_DIR = if ($env:UV_CACHE_DIR) { $env:UV_CACHE_DIR } else { Join-Path $ToolsDir "uv-cache" }
$env:UV_PYTHON_INSTALL_DIR = if ($env:UV_PYTHON_INSTALL_DIR) { $env:UV_PYTHON_INSTALL_DIR } else { Join-Path $ToolsDir "python" }
$env:PLAYWRIGHT_BROWSERS_PATH = if ($env:PLAYWRIGHT_BROWSERS_PATH) {
    $env:PLAYWRIGHT_BROWSERS_PATH
} else {
    Join-Path $ToolsDir "playwright"
}
$env:COREPACK_HOME = if ($env:COREPACK_HOME) { $env:COREPACK_HOME } else { Join-Path $ToolsDir "corepack" }
$env:Path = "$BinDir;$NodeDir;$env:Path"

$Failures = 0
$Warnings = 0
function Write-Ok([string]$Message) { Write-Host "[OK] $Message" -ForegroundColor Green }
function Write-WarningResult([string]$Message) {
    $script:Warnings += 1
    Write-Host "[!] $Message" -ForegroundColor Yellow
}
function Write-Failure([string]$Message) {
    $script:Failures += 1
    Write-Host "[X] $Message" -ForegroundColor Red
}

$UvBin = Join-Path $BinDir "uv.exe"
if (Test-Path $UvBin) {
    Write-Ok "uv: $(& $UvBin --version 2>$null)"
} else {
    Write-Failure "未找到项目内 uv（运行 scripts\bootstrap.ps1）"
}

$PythonBin = Join-Path $RootDir "backend\.venv\Scripts\python.exe"
if (Test-Path $PythonBin) {
    $PythonVersion = (& $PythonBin -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null)
    if ($PythonVersion -eq "3.12") {
        Write-Ok "Python 3.12: $PythonBin"
    } else {
        Write-Failure "后端虚拟环境不是 Python 3.12：$PythonVersion"
    }
} else {
    Write-Failure "后端虚拟环境尚未安装"
}

$NodeBin = Join-Path $NodeDir "node.exe"
if (Test-Path $NodeBin) {
    $NodeVersion = (& $NodeBin --version 2>$null)
    $NodeMajor = [int]((& $NodeBin -p "process.versions.node.split('.')[0]" 2>$null))
    if ($NodeMajor -ge 22) {
        Write-Ok "Node.js: $NodeVersion"
    } else {
        Write-Failure "Node.js $NodeVersion 低于项目基线 22"
    }
} else {
    Write-Failure "未找到项目内 Node.js"
}

$CorepackBin = Join-Path $NodeDir "corepack.cmd"
if (Test-Path $CorepackBin) {
    Push-Location (Join-Path $RootDir "web")
    try {
        $PnpmVersion = (& $CorepackBin pnpm --version 2>$null)
        if ($LASTEXITCODE -eq 0) {
            Write-Ok "pnpm: $PnpmVersion"
        } else {
            Write-Failure "corepack 无法启动 pnpm"
        }
    } finally {
        Pop-Location
    }
} else {
    Write-Failure "未找到项目内 corepack"
}

foreach ($Required in @(
    "backend\pyproject.toml",
    "backend\src\hi_agent\main.py",
    "web\package.json",
    "skills\knowledge-base-qa\SKILL.md",
    "deploy\vllm-compose.yml"
)) {
    if (-not (Test-Path (Join-Path $RootDir $Required))) {
        Write-Failure "缺少项目文件：$Required"
    }
}

if (Test-Path (Join-Path $RootDir ".env")) { Write-Ok ".env 已配置" } else {
    Write-WarningResult "尚未创建 .env，将使用安全默认值"
}
if (Test-Path (Join-Path $RootDir "web\dist\index.html")) { Write-Ok "Web 已构建" } else {
    Write-WarningResult "Web 尚未构建"
}
if (Test-Path $env:PLAYWRIGHT_BROWSERS_PATH) { Write-Ok "Playwright Chromium 已安装" } else {
    Write-WarningResult "Playwright 浏览器尚未安装"
}

$Docker = Get-Command docker -ErrorAction SilentlyContinue
if ($Docker) {
    & $Docker.Source compose version *> $null
    if ($LASTEXITCODE -eq 0) {
        Write-Ok "Docker Compose 可用（仅 Linux/NVIDIA 主机运行 vLLM）"
    } else {
        Write-WarningResult "Docker 可用，但 Compose 不可用；这不影响 Windows 作为 vLLM 客户端"
    }
} else {
    Write-WarningResult "Docker Compose 不可用；这不影响 Windows 作为 vLLM 客户端"
}

$PidFile = Join-Path $RootDir ".hi-agent.pid"
if (Test-Path $PidFile) {
    $StoredPid = 0
    if ([int]::TryParse((Get-Content $PidFile -Raw).Trim(), [ref]$StoredPid) -and
        (Get-Process -Id $StoredPid -ErrorAction SilentlyContinue)) {
        Write-Ok "Hi-agent 正在运行（PID $StoredPid）"
    } else {
        Write-WarningResult "发现失效的 .hi-agent.pid"
    }
}

Write-Host ""
Write-Host "诊断完成：$Failures 个错误，$Warnings 个提醒。"
if ($Failures -gt 0) { exit 1 }
exit 0
