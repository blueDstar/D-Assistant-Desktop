$projectRoot = Split-Path $PSScriptRoot -Parent
& (Join-Path $projectRoot '.venv\Scripts\python.exe') -X utf8 (Join-Path $PSScriptRoot 'diagnose.py')
