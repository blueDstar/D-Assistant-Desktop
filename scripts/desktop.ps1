param([switch]$Background)
$ErrorActionPreference = 'Stop'
$desktopRoot = Split-Path $PSScriptRoot -Parent
$desktopExe = Join-Path $desktopRoot 'artifacts\D-bot-Desktop\D-bot.exe'
if (-not (Test-Path -LiteralPath $desktopExe)) { throw 'Build desktop first: node scripts/build_desktop.cjs' }
# Electron must be an application even when launched from a Node-based editor.
Remove-Item Env:ELECTRON_RUN_AS_NODE -ErrorAction SilentlyContinue
$desktopArgs = @()
if ($Background) { $desktopArgs += '--background' }
if ($desktopArgs.Count) { Start-Process -FilePath $desktopExe -ArgumentList $desktopArgs -WorkingDirectory $desktopRoot -WindowStyle Hidden }
else { Start-Process -FilePath $desktopExe -WorkingDirectory $desktopRoot -WindowStyle Hidden }
