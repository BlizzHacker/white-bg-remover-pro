WHITE BG REMOVER PRO
====================

What it does
------------
This Windows desktop tool batch-processes character assets that were exported on white or gray backgrounds.
It produces:

1) output_png
   - transparent PNG cutouts
2) qa_previews
   - side-by-side before/after preview images for quality control
3) review_needed
   - copies of originals that the tool thinks should be checked by hand
4) failed
   - files that could not be processed
5) logs
   - processing_summary.csv with status and notes

Recommended use
---------------
This is designed for large batches, such as 889 fantasy character images that need prep work before image-to-3D conversion.

Suggested starting settings
---------------------------
- Background threshold: 36
- Edge choke (px): 1
- Feather (px): 1.25
- Canvas size: 1024
- Trim and center: ON

How to run the app (without building an EXE)
--------------------------------------------
1. Put this project folder somewhere on your PC.
2. Right-click run_app.ps1 and run it in PowerShell.
3. If Windows blocks PowerShell scripts, open PowerShell as admin and run:

   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

4. The script creates a local virtual environment, installs dependencies, and launches the GUI.

How to build the EXE
--------------------
1. Right-click build_exe.ps1 and run it in PowerShell.
2. Or open PowerShell in this folder and run:

   .\build_exe.ps1

3. When it finishes, your built app will be here:

   dist\WhiteBGRemoverPro.exe

Workflow inside the app
-----------------------
1. Choose your input folder.
2. Choose a workspace folder.
3. Click Start Batch.
4. Review:
   - output_png for your transparent results
   - qa_previews for side-by-side visual checks
   - review_needed for files that may need hand inspection
   - failed for anything that crashed or could not be parsed
   - logs\processing_summary.csv for a spreadsheet-style summary

Notes
-----
- This tool does NOT modify your originals in place.
- It is intended for white/gray studio-style backgrounds.
- Some highly complex edges, spell effects, fog, or pale translucent wings may still need manual review.

If you want to improve detection after a small test batch
---------------------------------------------------------
- Increase threshold if background is still visible.
- Decrease threshold if body parts or wing edges get cut off.
- Increase feather slightly if the edge looks too harsh.
- Increase choke to 2 if a faint white halo remains.
