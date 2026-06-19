param(
    [Parameter(Mandatory = $true)]
    [string]$Host,

    [Parameter(Mandatory = $true)]
    [string]$RemoteAudioToken,

    [Parameter(Mandatory = $true)]
    [string]$CaCertPath,

    [Parameter(Mandatory = $true)]
    [string]$VoskModelPath,

    [string]$TlsServerName,
    [string]$SourceId = "kitchen-node",
    [int]$Port = 45881,
    [string]$WakePhrase = "hey steven",
    [ValidateSet("phrase_vosk", "openwakeword")]
    [string]$WakeMode = "phrase_vosk",
    [switch]$EnableDebug
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
Set-Location $repoRoot

if ([string]::IsNullOrWhiteSpace($RemoteAudioToken) -or $RemoteAudioToken.Length -lt 16) {
    throw "Remote audio token must be at least 16 characters."
}
if (-not (Test-Path -Path $CaCertPath)) {
    throw "CA cert file not found: $CaCertPath"
}
if ($WakeMode -eq "phrase_vosk" -and -not (Test-Path -Path $VoskModelPath)) {
    throw "Vosk model path not found: $VoskModelPath"
}

$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -Path $pythonExe)) {
    $pythonExe = "python"
}

$env:FINANCE_APP_REMOTE_AUDIO_HOST = $Host
$env:FINANCE_APP_REMOTE_AUDIO_PORT = "$Port"
$env:FINANCE_APP_REMOTE_AUDIO_TOKEN = $RemoteAudioToken
$env:FINANCE_APP_REMOTE_AUDIO_CA_CERT = $CaCertPath
$env:FINANCE_APP_REMOTE_AUDIO_TLS_SERVER_NAME = $(if ([string]::IsNullOrWhiteSpace($TlsServerName)) { $Host } else { $TlsServerName })
$env:FINANCE_APP_REMOTE_SOURCE_ID = $SourceId
$env:FINANCE_APP_REMOTE_WAKE_MODE = $WakeMode
$env:FINANCE_APP_REMOTE_WAKE_PHRASE = $WakePhrase
$env:FINANCE_APP_REMOTE_VOSK_MODEL_PATH = $VoskModelPath

if ($EnableDebug) {
    $env:FINANCE_APP_REMOTE_DEBUG = "1"
}

Write-Host "Starting remote voice sender..."
Write-Host "Repo: $repoRoot"
Write-Host "Target: ${Host}:$Port"
Write-Host "Source ID: $SourceId"
Write-Host "Wake mode: $WakeMode"

$args = @("remote_voice_sender.py")
if ($EnableDebug) {
    $args += "--debug"
}

& $pythonExe @args
