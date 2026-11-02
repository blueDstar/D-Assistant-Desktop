param([switch]$Build, [switch]$OpenBrowser)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$runtimeDir = Join-Path $projectRoot '.runtime'
$logDir = Join-Path $projectRoot 'data\logs'
$statePath = Join-Path $runtimeDir 'processes.json'
New-Item -ItemType Directory -Force -Path $runtimeDir,$logDir | Out-Null
$port = 8008
$envFile = Join-Path $projectRoot '.env'
if (Test-Path $envFile) { foreach ($line in Get-Content $envFile) { if ($line -match '^DBOT_PORT=(\d+)$') { $port = [int]$Matches[1] } } }
$url = "http://127.0.0.1:$port"
function Is-Ready([string]$Address) { try { $backendProbe = $Address.EndsWith('/api/health'); if ($backendProbe) { $Address = $Address.Replace('/api/health','/api/session') }; $answer = Invoke-RestMethod -Uri $Address -TimeoutSec 10; if ($backendProbe) { return [bool]$answer.token -and $answer.token.Length -ge 16 }; return [bool]$answer.version } catch { return $false } }
if (Is-Ready "$url/api/health") { Write-Host "D-bot dang chay: $url"; if ($OpenBrowser) { Start-Process $url }; exit 0 }
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$ollamaPath = Join-Path $projectRoot '.runtime\ollama\ollama.exe'
if (-not (Test-Path $pythonPath)) { throw 'Chay scripts\setup.ps1 truoc.' }
if ($Build) {
    $env:PATH = (Join-Path $projectRoot '.runtime\node') + ';' + $env:PATH
    & (Join-Path $projectRoot '.runtime\node\npm.cmd') --prefix (Join-Path $projectRoot 'frontend') run build
    if ($LASTEXITCODE -ne 0) { throw 'Build that bai.' }
}
if (-not (Test-Path (Join-Path $projectRoot 'frontend\dist\index.html'))) { throw 'Chua co frontend build. Chay setup.ps1 hoac start.ps1 -Build.' }
$records = @()
if (Test-Path $statePath) { $decoded = Get-Content -Raw $statePath | ConvertFrom-Json; foreach ($entry in $decoded) { $records += $entry } }
function Record-Process($Process, [string]$Kind, [string]$Executable) {
    return [pscustomobject]@{ id=$Process.Id; kind=$Kind; executable=$Executable; started=$Process.StartTime.ToFileTimeUtc().ToString() }
}
if (-not (Is-Ready 'http://127.0.0.1:11434/api/version')) {
    if (-not (Test-Path $ollamaPath)) { throw 'Chua co Ollama portable. Chay setup.ps1.' }
    $env:OLLAMA_NO_CLOUD = '1'
    $env:OLLAMA_HOST = '127.0.0.1:11434'
    $env:OLLAMA_MODELS = Join-Path $projectRoot 'data\models\ollama'
    $env:OLLAMA_NUM_PARALLEL = '1'
    $env:OLLAMA_MAX_LOADED_MODELS = '1'
    $env:OLLAMA_CONTEXT_LENGTH = '4096'
    $env:OLLAMA_MAX_QUEUE = '8'
    $stopOllama = Join-Path $runtimeDir 'stop-ollama'
    if (Test-Path $stopOllama) { Remove-Item -LiteralPath $stopOllama }
    $process = Start-Process -FilePath $pythonPath -ArgumentList @('-X','utf8', ('"' + (Join-Path $projectRoot 'scripts\ollama_supervisor.py') + '"')) -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logDir 'ollama.out.log') -RedirectStandardError (Join-Path $logDir 'ollama.err.log') -PassThru
    $records += Record-Process $process 'ollama' $pythonPath
    $records | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $statePath -Encoding UTF8
    $ollamaReady = $false
    for ($i=0; $i -lt 30; $i++) { if (Is-Ready 'http://127.0.0.1:11434/api/version') { $ollamaReady=$true; break }; Start-Sleep -Milliseconds 500 }
    if (-not $ollamaReady) { throw 'Ollama chua san sang. Xem data\logs\ollama.err.log.' }
} else { Write-Host 'Tai su dung Ollama dang chay. Neu khong do launcher nay tao, can tu kiem tra cloud disabled trong log.' }
$stopFile = Join-Path $runtimeDir 'stop-backend'
if (Test-Path $stopFile) { Remove-Item -LiteralPath $stopFile }
$process = Start-Process -FilePath $pythonPath -ArgumentList @('-X','utf8', ('"' + (Join-Path $projectRoot 'scripts\serve.py') + '"')) -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logDir 'backend.out.log') -RedirectStandardError (Join-Path $logDir 'backend.err.log') -PassThru
$records += Record-Process $process 'backend' $pythonPath
$records | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $statePath -Encoding UTF8
$backendReady = $false
for ($i=0; $i -lt 40; $i++) { if (Is-Ready "$url/api/health") { $backendReady=$true; break }; Start-Sleep -Milliseconds 500 }
if (-not $backendReady) { throw 'Backend chua san sang. Xem data\logs\backend.err.log.' }
Write-Host "D-bot: $url"
Write-Host 'Dung app bang scripts\stop.ps1. Chon model da tai trong Cai dat.'
if ($OpenBrowser) { Start-Process $url }
