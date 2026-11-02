$ErrorActionPreference = 'Stop'
$shortcutRoot = Split-Path $PSScriptRoot -Parent
$shortcutExe = Join-Path $shortcutRoot 'artifacts\D-bot-Desktop\D-bot.exe'
$shortcutIcon = Join-Path $shortcutRoot 'desktop\icon.ico'
if (-not (Test-Path -LiteralPath $shortcutExe)) { throw 'Build D-bot Desktop first.' }
$shortcutShell = New-Object -ComObject WScript.Shell
$shortcutDirectory = $shortcutShell.SpecialFolders.Item('Desktop')
$shortcutPath = Join-Path $shortcutDirectory 'D-bot Assistant.lnk'
# This deliberately writes only one named shortcut; no startup/registry changes.
$shortcut = $shortcutShell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $shortcutExe
$shortcut.WorkingDirectory = $shortcutRoot
$shortcut.IconLocation = $shortcutIcon
$shortcut.Description = 'D-bot Assistant - local AI and desktop companion'
$shortcut.Save()
Write-Output $shortcutPath
