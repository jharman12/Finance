param(
    [Parameter(Mandatory = $true)]
    [string]$RemoteAudioToken,

    [Parameter(Mandatory = $true)]
    [string]$TlsCertPath,

    [Parameter(Mandatory = $true)]
    [string]$TlsKeyPath,

    [string]$BindHost = "0.0.0.0",
    [int]$Port = 45881,
    [switch]$EnableRemoteDebug
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
Set-Location $repoRoot

if (-not (Test-Path -Path $TlsCertPath)) {
    throw "TLS cert file not found: $TlsCertPath"
}
if (-not (Test-Path -Path $TlsKeyPath)) {
    throw "TLS key file not found: $TlsKeyPath"
}
if ([string]::IsNullOrWhiteSpace($RemoteAudioToken) -or $RemoteAudioToken.Length -lt 16) {
    throw "Remote audio token must be at least 16 characters."
}

$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -Path $pythonExe)) {
    $pythonExe = "python"
}

$env:FINANCE_APP_REMOTE_AUDIO_ENABLED = "1"
$env:FINANCE_APP_REMOTE_AUDIO_TOKEN = $RemoteAudioToken
$env:FINANCE_APP_REMOTE_AUDIO_BIND_HOST = $BindHost
$env:FINANCE_APP_REMOTE_AUDIO_PORT = "$Port"
$env:FINANCE_APP_REMOTE_AUDIO_TLS_CERT = $TlsCertPath
$env:FINANCE_APP_REMOTE_AUDIO_TLS_KEY = $TlsKeyPath
$env:FINANCE_APP_LOCAL_MIC_ENABLED = "1"

if ($EnableRemoteDebug) {
    $env:FINANCE_APP_REMOTE_AUDIO_DEBUG = "1"
}

Write-Host "Starting Finance app with remote audio enabled..."
Write-Host "Repo: $repoRoot"
Write-Host "Bind: ${BindHost}:$Port"
Write-Host "TLS cert: $TlsCertPath"

& $pythonExe "main.py"
