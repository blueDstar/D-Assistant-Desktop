param([switch]$SkipVoice)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Push-Location $projectRoot
try {
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw 'Cần Python >= 3.9 để chuẩn bị runtime portable. Không đổi Python toàn máy.' }
    if (-not (Test-Path '.runtime\node\node.exe') -or -not (Test-Path '.runtime\uv\uv.exe') -or -not (Test-Path '.runtime\ollama\ollama.exe')) {
        python scripts\bootstrap_runtime.py
        if ($LASTEXITCODE -ne 0) { throw 'Không tải được runtime. Kiểm tra kết nối Internet.' }
    }
    $env:UV_CACHE_DIR = Join-Path $projectRoot '.runtime\uv-cache'
    $env:UV_PYTHON_INSTALL_DIR = Join-Path $projectRoot '.runtime\python'
    $env:UV_PROJECT_ENVIRONMENT = Join-Path $projectRoot '.venv'
    $env:npm_config_cache = Join-Path $projectRoot '.runtime\npm-cache'
    $env:PATH = (Join-Path $projectRoot '.runtime\node') + ';' + $env:PATH
    $groups = @('--all-groups')
    if ($SkipVoice) { $groups = @('--group','dev') }
    & .runtime\uv\uv.exe sync --project backend --locked @groups
    if ($LASTEXITCODE -ne 0) { throw 'Cài dependency Python thất bại.' }
    & .runtime\node\npm.cmd --prefix frontend ci --no-fund --no-audit --ignore-scripts
    if ($LASTEXITCODE -ne 0) { throw 'Cài frontend thất bại.' }
    & .runtime\node\npm.cmd --prefix frontend run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build thất bại.' }
    if (-not (Test-Path '.env')) { Copy-Item -LiteralPath '.env.example' -Destination '.env' }
    Write-Host 'Setup xong. Chuan bi voice/model bang prepare_models.py --voice, prepare_models_v6.py va prepare_language_tts.py. Xem docs/INSTALLATION.md de import Qwen3.5 vao Ollama roi mo desktop.'
} finally { Pop-Location }
