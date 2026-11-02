$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$statePath = Join-Path $projectRoot '.runtime\processes.json'
if (-not (Test-Path $statePath)) { Write-Host 'Khong co process do launcher quan ly.'; exit 0 }
$records = Get-Content -Raw $statePath | ConvertFrom-Json
$remaining = @()
foreach ($record in ($records | Sort-Object { if ($_.kind -eq 'backend') { 0 } else { 1 } })) {
    $process = Get-Process -Id $record.id -ErrorAction SilentlyContinue
    if (-not $process) { continue }
    $expected = if ($record.kind -in @('backend','ollama')) { Join-Path $projectRoot '.venv\Scripts\python.exe' } else { '' }
    if (-not $expected -or $process.Path -ne $expected -or $process.StartTime.ToFileTimeUtc().ToString() -ne $record.started) { Write-Warning "Bo qua PID $($record.id): khong khop executable/start time."; $remaining += $record; continue }
    $stopName = if ($record.kind -eq 'backend') { '.runtime\stop-backend' } else { '.runtime\stop-ollama' }
    Set-Content -LiteralPath (Join-Path $projectRoot $stopName) -Value 'stop'
    for ($i=0; $i -lt 30; $i++) { if ($process.HasExited) { break }; Start-Sleep -Milliseconds 500; $process.Refresh() }
    if (-not $process.HasExited) {
        # Only the verified process created by this launcher, and its children.
        & taskkill.exe /PID $record.id /T /F | Out-Null
        if ($LASTEXITCODE -ne 0) { $remaining += $record }
    }
}
if ($remaining.Count) { $remaining | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $statePath -Encoding UTF8; throw 'Con process chua dung duoc; da giu lai state. Xem log, khong kill Python/Ollama khac.' }
Remove-Item -LiteralPath $statePath
Write-Host 'Da dung cac process duoc launcher xac nhan. Khong dung Python/Node/Ollama khac.'
