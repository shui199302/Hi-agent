[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$PidFile = Join-Path $PSScriptRoot ".hi-agent.pid"

if (-not (Test-Path $PidFile)) {
    Write-Host "Hi-agent 当前没有由启动脚本启动的进程。"
    exit 0
}

$StoredPid = 0
$PidValue = (Get-Content $PidFile -Raw).Trim()
if (-not [int]::TryParse($PidValue, [ref]$StoredPid)) {
    Remove-Item $PidFile -Force
    throw "PID 文件内容无效，已清理。"
}

$Process = Get-Process -Id $StoredPid -ErrorAction SilentlyContinue
if ($Process) {
    $CommandLine = $null
    try {
        $CommandLine = (Get-CimInstance Win32_Process -Filter "ProcessId = $StoredPid").CommandLine
    } catch {
        throw "无法确认 PID $StoredPid 的进程身份；为避免停止其他进程，请手工检查任务管理器。"
    }
    if (-not $CommandLine -or -not $CommandLine.Contains("serve.py")) {
        Remove-Item $PidFile -Force
        throw "PID $StoredPid 不属于 Hi-agent，已清理失效 PID 文件。"
    }
    Stop-Process -Id $StoredPid
    Wait-Process -Id $StoredPid -Timeout 5 -ErrorAction SilentlyContinue
}

Remove-Item $PidFile -Force
Write-Host "Hi-agent 已停止。"
