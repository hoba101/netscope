# NetScope Windows build script
# Copyright (c) 2026 miro (hoba101)
# Requires: Python 3.10+, pip, pyinstaller, psutil

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $Root

python -m pip install --upgrade pip
python -m pip install pyinstaller psutil pygobject; if ($LASTEXITCODE -ne 0) { Write-Host 'PyGObject/GTK may require MSYS2 on Windows for full GUI; CLI/backend packaging can still proceed.' }
python -m pip install .

python -m PyInstaller --noconfirm --clean --name NetScope --onefile --windowed --icon assets/icons/hicolor/scalable/apps/io.github.hoba101.NetScope.svg -m netscope
Write-Host "Build output: $Root\dist\NetScope.exe"
