# Build the Windows single-file EXE.
# Usage: powershell -ExecutionPolicy Bypass -File scripts/build_exe.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

python -m pip install pyinstaller
python -m PyInstaller --noconfirm --clean WebScanSOP.spec

Write-Host ""
Write-Host "Built: $root\dist\WebScanSOP.exe" -ForegroundColor Green
Get-Item "$root\dist\WebScanSOP.exe" | Select-Object Name, Length, LastWriteTime
