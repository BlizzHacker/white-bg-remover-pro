# White BG Remover Pro

Windows desktop batch background remover for white/gray character assets.

## Features
- Batch removes white/gray backgrounds
- Exports transparent PNGs
- Creates QA previews
- Sorts review-needed and failed files
- Writes CSV logs
- Trims and centers assets on square canvas

## Run
PowerShell -ExecutionPolicy Bypass -File .\run_app.ps1

## Build EXE
PowerShell -ExecutionPolicy Bypass -File .\build_exe.ps1

Use Python 3.12 for building the EXE. Python 3.13 can break PyInstaller/Tkinter packaging.

## Release
Normal users can download WhiteBGRemoverPro-v1.0.0.zip and run WhiteBGRemoverPro.exe.
