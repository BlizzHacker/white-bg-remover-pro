# White BG Remover Pro

A project of the [Move Weight Foundation](https://foundation.moveweight.com), an
Oklahoma non-profit corporation with 501(c)(3) status pending.

A Windows batch tool that cuts white and gray backgrounds off character art,
leaving clean transparent PNGs — hundreds of files at a time, with QA previews
so you can trust a batch without eyeballing every image.

It exists because AI image generators hand you piles of assets on flat white
backgrounds, and removing them one at a time in an editor is not a workflow.
Point it at a folder and it does the whole pile, and — this is the part that
matters — it tells you which files it *wasn't* sure about instead of quietly
shipping a bad cut.

## What a batch gives you

- Transparent PNGs, trimmed and centered on a square canvas
- A QA preview per file, so a spot-check is a glance
- Files it wasn't confident about sorted into **review-needed**, and failures
  into their own folder — never mixed in with the good output
- A CSV log of everything it did

## Download and run

1. Grab `WhiteBGRemoverPro-v1.0.0.zip` from
   [Releases](https://github.com/BlizzHacker/white-bg-remover-pro/releases/latest).
2. Unzip anywhere and run `WhiteBGRemoverPro.exe` — no installer, no admin.
3. Pick your input folder and start the batch.

## Run from source

```powershell
PowerShell -ExecutionPolicy Bypass -File .\run_app.ps1
```

## Build the EXE

```powershell
PowerShell -ExecutionPolicy Bypass -File .\build_exe.ps1
```

Use **Python 3.12** for building — Python 3.13 can break PyInstaller/Tkinter
packaging.
