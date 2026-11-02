param([string]$Model = '', [switch]$Voice)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
if (-not $Model -and -not $Voice) { Write-Host 'Chon -Model qwen3:1.7b (~1.4 GB), qwen3:4b-instruct (~2.5 GB) hoac -Voice (Whisper base + Piper vi, ~210 MB). Khong tu tai model.'; exit 0 }
if ($Model -and ($Model -notmatch '^[A-Za-z0-9_.:-]+$' -or $Model -match 'cloud')) { throw 'Chi chon tag model local, khong cloud.' }
& (Join-Path $PSScriptRoot 'start.ps1')
if ($Model) {
    Write-Host "Tai model da chon: $Model. Model dat trong data\models\ollama cua server do launcher tao."
    $body = @{ model=$Model; stream=$false } | ConvertTo-Json
    $null = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:11434/api/pull' -ContentType 'application/json' -Body $body -TimeoutSec 3600
    & (Join-Path $projectRoot '.venv\Scripts\python.exe') -X utf8 (Join-Path $PSScriptRoot 'prepare_models.py') --tokenizer
    if ($LASTEXITCODE -ne 0) { throw 'Chua tai du tokenizer.' }
    if ($Model -like 'qwen3:*') {
        & (Join-Path $projectRoot '.venv\Scripts\python.exe') -X utf8 (Join-Path $PSScriptRoot 'probe_tools.py') --model $Model
        if ($LASTEXITCODE -ne 0) { Write-Warning 'Probe cong cu chua thanh cong; chat/RAG va cong cu qua UI van dung duoc.' }
    }
}
if ($Voice) {
    & (Join-Path $projectRoot '.venv\Scripts\python.exe') -X utf8 (Join-Path $PSScriptRoot 'prepare_models.py') --voice
    if ($LASTEXITCODE -ne 0) { throw 'Chua tai du model/voice.' }
}
Write-Host 'Tai xong tai san da chon. Runtime khong tu tai model khi offline.'
