$ErrorActionPreference = 'Stop'

Write-Host '== White BG Remover Pro - Run Script ==' -ForegroundColor Cyan
Set-Location $PSScriptRoot

if (-not (Test-Path .venv)) {
    py -m venv .venv
}

& .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python .\app.py
