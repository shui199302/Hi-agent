[CmdletBinding()]
param(
    [switch]$SkipBrowserDownload,
    [switch]$SkipModelDownload
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$RootDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ToolsDir = Join-Path $RootDir ".tools"
$BinDir = Join-Path $ToolsDir "bin"
$NodeDir = Join-Path $ToolsDir "node"
$NodeVersion = "22.17.0"
$PnpmVersion = "11.7.0"

function Write-Note([string]$Message) {
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Invoke-Checked([string]$FilePath, [string[]]$ArgumentList) {
    & $FilePath @ArgumentList
    if ($LASTEXITCODE -ne 0) {
        throw "命令执行失败（退出码 $LASTEXITCODE）：$FilePath $($ArgumentList -join ' ')"
    }
}

function Test-Enabled([string]$Value) {
    return $Value -match "^(1|true|yes|on)$"
}

if (-not [Environment]::Is64BitOperatingSystem -or $env:PROCESSOR_ARCHITECTURE -notin @("AMD64", "x86")) {
    throw "当前安装脚本支持 Windows 10/11 x64；Windows ARM64 尚未完成依赖兼容性验证。"
}

New-Item -ItemType Directory -Path $BinDir -Force | Out-Null
$env:UV_CACHE_DIR = if ($env:UV_CACHE_DIR) { $env:UV_CACHE_DIR } else { Join-Path $ToolsDir "uv-cache" }
$env:UV_PYTHON_INSTALL_DIR = if ($env:UV_PYTHON_INSTALL_DIR) { $env:UV_PYTHON_INSTALL_DIR } else { Join-Path $ToolsDir "python" }
$env:PLAYWRIGHT_BROWSERS_PATH = if ($env:PLAYWRIGHT_BROWSERS_PATH) {
    $env:PLAYWRIGHT_BROWSERS_PATH
} else {
    Join-Path $ToolsDir "playwright"
}
$env:COREPACK_HOME = if ($env:COREPACK_HOME) { $env:COREPACK_HOME } else { Join-Path $ToolsDir "corepack" }
$env:Path = "$BinDir;$NodeDir;$env:Path"

$UvBin = Join-Path $BinDir "uv.exe"
if (-not (Test-Path $UvBin)) {
    $Installer = Join-Path ([IO.Path]::GetTempPath()) "hi-agent-uv-$([guid]::NewGuid()).ps1"
    try {
        Write-Note "从 astral.sh 下载 uv 安装器"
        Invoke-WebRequest -UseBasicParsing -Uri "https://astral.sh/uv/install.ps1" -OutFile $Installer
        $env:UV_INSTALL_DIR = $BinDir
        $env:UV_NO_MODIFY_PATH = "1"
        Invoke-Checked "powershell.exe" @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $Installer)
    } finally {
        Remove-Item $Installer -Force -ErrorAction SilentlyContinue
    }
}
if (-not (Test-Path $UvBin)) {
    throw "uv 安装失败：未找到 $UvBin"
}

$NodeBin = Join-Path $NodeDir "node.exe"
if (-not (Test-Path $NodeBin)) {
    $Archive = "node-v$NodeVersion-win-x64.zip"
    $BaseUrl = "https://nodejs.org/dist/v$NodeVersion"
    $WorkDir = Join-Path ([IO.Path]::GetTempPath()) "hi-agent-node-$([guid]::NewGuid())"
    New-Item -ItemType Directory -Path $WorkDir -Force | Out-Null
    try {
        $ArchivePath = Join-Path $WorkDir $Archive
        $ChecksumsPath = Join-Path $WorkDir "SHASUMS256.txt"
        Write-Note "下载并校验 Node.js $NodeVersion x64"
        Invoke-WebRequest -UseBasicParsing -Uri "$BaseUrl/$Archive" -OutFile $ArchivePath
        Invoke-WebRequest -UseBasicParsing -Uri "$BaseUrl/SHASUMS256.txt" -OutFile $ChecksumsPath

        $ExpectedHash = $null
        foreach ($Line in Get-Content $ChecksumsPath) {
            $Parts = $Line -split "\s+"
            if ($Parts.Count -ge 2 -and $Parts[-1].TrimStart("*") -eq $Archive) {
                $ExpectedHash = $Parts[0]
                break
            }
        }
        if (-not $ExpectedHash) {
            throw "Node.js 校验清单中没有 $Archive"
        }
        $ActualHash = (Get-FileHash -Algorithm SHA256 $ArchivePath).Hash
        if ($ActualHash -ne $ExpectedHash) {
            throw "Node.js 下载校验失败"
        }

        Expand-Archive -Path $ArchivePath -DestinationPath $WorkDir -Force
        $ExtractedDir = Join-Path $WorkDir "node-v$NodeVersion-win-x64"
        Remove-Item $NodeDir -Recurse -Force -ErrorAction SilentlyContinue
        Move-Item $ExtractedDir $NodeDir
    } finally {
        Remove-Item $WorkDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}

$env:Path = "$BinDir;$NodeDir;$env:Path"
Invoke-Checked $NodeBin @("-e", "if (Number(process.versions.node.split('.')[0]) < 22) process.exit(1)")
$CorepackBin = Join-Path $NodeDir "corepack.cmd"
if (-not (Test-Path $CorepackBin)) {
    throw "项目内 Node.js 缺少 corepack"
}
Write-Note "启用项目内 pnpm $PnpmVersion"
Invoke-Checked $CorepackBin @("prepare", "pnpm@$PnpmVersion", "--activate")

Push-Location (Join-Path $RootDir "web")
try {
    $InstalledPnpmVersion = (& $CorepackBin pnpm --version).Trim()
    if ($LASTEXITCODE -ne 0 -or $InstalledPnpmVersion -ne $PnpmVersion) {
        throw "项目内 pnpm 版本不正确：$InstalledPnpmVersion"
    }
} finally {
    Pop-Location
}

Write-Note "安装 Python 3.12 和后端依赖"
Invoke-Checked $UvBin @("python", "install", "3.12")
Invoke-Checked $UvBin @("sync", "--project", (Join-Path $RootDir "backend"), "--frozen", "--all-extras", "--dev")
Write-Note "安装只读 MCP 示例服务器"
Invoke-Checked $UvBin @("sync", "--project", (Join-Path $RootDir "mcp_servers"), "--frozen", "--dev")

Write-Note "安装并构建 Web 控制台"
Push-Location (Join-Path $RootDir "web")
try {
    Invoke-Checked $CorepackBin @("pnpm", "install", "--frozen-lockfile")
    Invoke-Checked $CorepackBin @("pnpm", "build")
    $SkipBrowser = $SkipBrowserDownload -or (Test-Enabled $env:HI_AGENT_SKIP_BROWSER_DOWNLOAD)
    if (-not $SkipBrowser) {
        Write-Note "安装 Playwright Chromium 端到端测试浏览器"
        Invoke-Checked $CorepackBin @("pnpm", "exec", "playwright", "install", "chromium")
    }
} finally {
    Pop-Location
}

$SkipModel = $SkipModelDownload -or (Test-Enabled $env:HI_AGENT_SKIP_MODEL_DOWNLOAD)
if (-not $SkipModel) {
    Write-Note "预下载中文嵌入模型（不会下载大语言模型）"
    Invoke-Checked $UvBin @(
        "run", "--project", (Join-Path $RootDir "backend"),
        "python", (Join-Path $RootDir "scripts\preload_embedding.py")
    )
}

Write-Note "运行环境诊断"
& (Join-Path $PSScriptRoot "doctor.ps1")
if (-not $?) {
    throw "环境诊断未通过"
}
Write-Note "安装完成。复制 .env.example 为 .env 后运行 .\start.ps1"
