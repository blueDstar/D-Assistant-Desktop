$ErrorActionPreference = 'SilentlyContinue'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$installedRows = New-Object 'System.Collections.Generic.List[object]'
foreach ($installedHive in @([Microsoft.Win32.RegistryHive]::CurrentUser,[Microsoft.Win32.RegistryHive]::LocalMachine)) {
  foreach ($installedView in @([Microsoft.Win32.RegistryView]::Registry64,[Microsoft.Win32.RegistryView]::Registry32)) {
    $installedBase = [Microsoft.Win32.RegistryKey]::OpenBaseKey($installedHive,$installedView)
    $installedPaths = $installedBase.OpenSubKey('Software\Microsoft\Windows\CurrentVersion\App Paths')
    if ($installedPaths) {
      foreach ($installedName in $installedPaths.GetSubKeyNames()) {
        $installedKey = $installedPaths.OpenSubKey($installedName)
        $installedTarget = ([string]$installedKey.GetValue('')).Trim('"')
        if ($installedTarget -match '\.exe$' -and (Test-Path -LiteralPath $installedTarget -PathType Leaf)) { $installedRows.Add([pscustomobject]@{name=[IO.Path]::GetFileNameWithoutExtension($installedName);exe=$installedTarget;source='App Paths'}) }
        $installedKey.Close()
      }
      $installedPaths.Close()
    }
    $installedBase.Close()
  }
}
$installedShell = New-Object -ComObject WScript.Shell
$installedMenus = @([Environment]::GetFolderPath('Programs'),[Environment]::GetFolderPath('CommonPrograms'))
foreach ($installedMenu in $installedMenus) {
  if (-not $installedMenu) { continue }
  foreach ($installedLink in (Get-ChildItem -LiteralPath $installedMenu -Filter '*.lnk' -File -Recurse | Select-Object -First 500)) {
    $installedShortcut = $installedShell.CreateShortcut($installedLink.FullName)
    $installedTarget = [Environment]::ExpandEnvironmentVariables($installedShortcut.TargetPath)
    if (-not $installedShortcut.Arguments -and $installedTarget -match '\.exe$' -and (Test-Path -LiteralPath $installedTarget -PathType Leaf)) { $installedRows.Add([pscustomobject]@{name=$installedLink.BaseName;exe=$installedTarget;source='Start menu'}) }
  }
}
ConvertTo-Json -InputObject @($installedRows.ToArray() | Sort-Object exe,name -Unique) -Compress
