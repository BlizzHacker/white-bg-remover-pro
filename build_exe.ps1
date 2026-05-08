$ErrorActionPreference = 'Stop'

Write-Host '== White BG Remover Pro - Build Script ==' -ForegroundColor Cyan
Set-Location $PSScriptRoot

if (-not (Test-Path .venv)) {
    py -m venv .venv
}

& .\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
pip install -r requirements.txt pyinstaller

python -c "import tkinter; print('Tkinter OK')"

if (Test-Path build) {
    Remove-Item build -Recurse -Force
}

if (Test-Path dist) {
    Remove-Item dist -Recurse -Force
}

if (Test-Path WhiteBGRemoverPro.spec) {
    Remove-Item WhiteBGRemoverPro.spec -Force
}

pyinstaller `
  --noconfirm `
  --clean `
  --windowed `
  --onefile `
  --name WhiteBGRemoverPro `
  --icon assets\icon.ico `
  --hidden-import tkinter `
  --hidden-import tkinter.ttk `
  --collect-submodules tkinter `
  app.py

Write-Host ''
Write-Host 'Build complete.' -ForegroundColor Green
Write-Host 'Your EXE is here:' -ForegroundColor Yellow
Write-Host (Join-Path $PSScriptRoot 'dist\WhiteBGRemoverPro.exe')