[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$RootDir = $PSScriptRoot
$ToolsDir = Join-Path $RootDir ".tools"
$NodeDir = Join-Path $ToolsDir "node"
$env:UV_CACHE_DIR = if ($env:UV_CACHE_DIR) { $env:UV_CACHE_DIR } else { Join-Path $ToolsDir "uv-cache" }
$env:UV_PYTHON_INSTALL_DIR = if ($env:UV_PYTHON_INSTALL_DIR) { $env:UV_PYTHON_INSTALL_DIR } else { Join-Path $ToolsDir "python" }
$env:COREPACK_HOME = if ($env:COREPACK_HOME) { $env:COREPACK_HOME } else { Join-Path $ToolsDir "corepack" }
$env:Path = "$(Join-Path $ToolsDir 'bin');$NodeDir;$env:Path"

function Test-SourceNewer([string[]]$Paths, [datetime]$Baseline) {
    foreach ($Path in $Paths) {
        if (-not (Test-Path $Path)) { continue }
        $Item = Get-Item $Path
        if (-not $Item.PSIsContainer -and $Item.LastWriteTimeUtc -gt $Baseline) { return $true }
        if ($Item.PSIsContainer -and (Get-ChildItem $Path -File -Recurse | Where-Object {
            $_.LastWriteTimeUtc -gt $Baseline
        } | Select-Object -First 1)) { return $true }
    }
    return $false
}

function Get-HiAgentProcess([int]$ProcessId) {
    $Process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if (-not $Process) { return $null }
    try {
        $CommandLine = (Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId").CommandLine
        if ($CommandLine -and $CommandLine.Contains("serve.py")) { return $Process }
    } catch {
        return $null
    }
    return $null
}

$PythonBin = Join-Path $RootDir "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $PythonBin)) {
    throw "未找到后端环境。请先运行 powershell -ExecutionPolicy Bypass -File .\scripts\bootstrap.ps1"
}

$DistIndex = Join-Path $RootDir "web\dist\index.html"
$WebNeedsBuild = -not (Test-Path $DistIndex)
if (-not $WebNeedsBuild) {
    $WebNeedsBuild = Test-SourceNewer @(
        (Join-Path $RootDir "web\src"),
        (Join-Path $RootDir "web\index.html"),
        (Join-Path $RootDir "web\package.json"),
        (Join-Path $RootDir "web\pnpm-lock.yaml")
    ) (Get-Item $DistIndex).LastWriteTimeUtc
}
if ($WebNeedsBuild) {
    $CorepackBin = Join-Path $NodeDir "corepack.cmd"
    if (-not (Test-Path $CorepackBin)) {
        throw "Web 需要重新构建，但未找到项目内 corepack。请先运行安装脚本。"
    }
    Write-Host "检测到 Web 源码更新，正在重新构建…"
    Push-Location (Join-Path $RootDir "web")
    try {
        & $CorepackBin pnpm build
        if ($LASTEXITCODE -ne 0) { throw "Web 构建失败" }
    } finally {
        Pop-Location
    }
}

New-Item -ItemType Directory -Path (Join-Path $RootDir "logs"), (Join-Path $RootDir "data") -Force | Out-Null
$ServePath = Join-Path $RootDir "scripts\serve.py"
$AppUrl = (& $PythonBin $ServePath --print-url).Trim()
if ($LASTEXITCODE -ne 0 -or -not $AppUrl) { throw "无法读取 Hi-agent 服务地址" }

$PidFile = Join-Path $RootDir ".hi-agent.pid"
if (Test-Path $PidFile) {
    $ExistingPid = 0
    $PidValue = (Get-Content $PidFile -Raw).Trim()
    $ExistingProcess = $null
    if ([int]::TryParse($PidValue, [ref]$ExistingPid)) {
        $ExistingProcess = Get-HiAgentProcess $ExistingPid
    }
    if ($ExistingProcess) {
        $BackendNeedsRestart = Test-SourceNewer @(
            (Join-Path $RootDir "backend\src"),
            $ServePath,
            (Join-Path $RootDir "backend\pyproject.toml"),
            (Join-Path $RootDir "backend\uv.lock"),
            (Join-Path $RootDir ".env")
        ) (Get-Item $PidFile).LastWriteTimeUtc
        if (-not $BackendNeedsRestart) {
            Write-Host "Hi-agent 已在运行：$AppUrl"
            Start-Process $AppUrl
            exit 0
        }
        Write-Host "检测到后端源码或配置更新，正在重启 Hi-agent…"
        Stop-Process -Id $ExistingPid
        Wait-Process -Id $ExistingPid -Timeout 5 -ErrorAction SilentlyContinue
    }
    Remove-Item $PidFile -Force
}

$StdoutLog = Join-Path $RootDir "logs\hi-agent.log"
$StderrLog = Join-Path $RootDir "logs\hi-agent.error.log"
Write-Host "正在启动 Hi-agent…"
$Server = Start-Process -FilePath $PythonBin -ArgumentList ('"{0}"' -f $ServePath) `
    -WorkingDirectory $RootDir -RedirectStandardOutput $StdoutLog -RedirectStandardError $StderrLog `
    -WindowStyle Hidden -PassThru
Set-Content -Path $PidFile -Value $Server.Id -Encoding Ascii

for ($Attempt = 0; $Attempt -lt 60; $Attempt += 1) {
    try {
        Invoke-WebRequest -UseBasicParsing -Uri "$AppUrl/api/v1/health" -TimeoutSec 2 | Out-Null
        Write-Host "Hi-agent 已启动：$AppUrl"
        Start-Process $AppUrl
        exit 0
    } catch {
        if ($Server.HasExited) {
            Write-Host "启动失败，最近日志：" -ForegroundColor Red
            Get-Content $StdoutLog, $StderrLog -Tail 40 -ErrorAction SilentlyContinue
            Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
            exit 1
        }
        Start-Sleep -Milliseconds 500
    }
}

Write-Host "启动超时，最近日志：" -ForegroundColor Red
Get-Content $StdoutLog, $StderrLog -Tail 40 -ErrorAction SilentlyContinue
Stop-Process -Id $Server.Id -ErrorAction SilentlyContinue
Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
exit 1
