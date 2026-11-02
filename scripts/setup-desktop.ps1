param([switch]$BuildUI)
$ErrorActionPreference = 'Stop'
$desktopRoot = Split-Path $PSScriptRoot -Parent
$desktopNode = Join-Path $desktopRoot '.runtime\node\node.exe'
$desktopNpm = Join-Path $desktopRoot '.runtime\node\npm.cmd'
$desktopPython = Join-Path $desktopRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $desktopNode)) { throw 'Run scripts/setup.ps1 first.' }
$env:PATH = (Split-Path $desktopNode -Parent) + ';' + $env:PATH
$env:npm_config_cache = Join-Path $desktopRoot '.runtime\npm-cache'
$env:ELECTRON_CACHE = Join-Path $desktopRoot '.runtime\electron-cache'
$env:electron_config_cache = $env:ELECTRON_CACHE
& $desktopNpm --prefix (Join-Path $desktopRoot 'desktop') ci --no-audit --no-fund
if ($LASTEXITCODE -ne 0) { throw 'Desktop npm ci failed.' }
& $desktopNode (Join-Path $desktopRoot 'desktop\node_modules\electron\install.js')
if ($LASTEXITCODE -ne 0) { throw 'Electron runtime download failed.' }
& $desktopPython -X utf8 (Join-Path $desktopRoot 'scripts\generate_desktop_icon.py')
if ($LASTEXITCODE -ne 0) { throw 'Icon generation failed.' }
if ($BuildUI -or -not (Test-Path (Join-Path $desktopRoot 'frontend\dist\index.html'))) {
    & $desktopNpm --prefix (Join-Path $desktopRoot 'frontend') run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
}
& $desktopNode (Join-Path $desktopRoot 'scripts\build_desktop.cjs')
if ($LASTEXITCODE -ne 0) { throw 'Desktop build failed.' }
Write-Host 'Ready: scripts/desktop.ps1. Desktop shortcut: scripts/install-desktop-shortcut.ps1'
