@echo off
REM ─────────────────────────────────────────────────────────────
REM  build_windows.bat — builds the final VideoCheck-Setup.exe
REM  Must be run ON Windows (PyInstaller can't cross-compile).
REM
REM  Usage:
REM    1. Install Python 3.10+ on your build machine.
REM    2. (Optional but recommended) Install Inno Setup (free):
REM       https://jrsoftware.org/isdl.php
REM    3. cd installer
REM    4. build_windows.bat
REM
REM  Two possible outputs, depending on whether Inno Setup is installed:
REM    - WITH Inno Setup:    dist\VideoCheck-Setup.exe
REM         A real Windows installer wizard: Welcome, progress, Finish
REM         screen with "Launch now" checkbox, Start Menu + Desktop icon,
REM         and a proper uninstaller in "Add or Remove Programs". This is
REM         the file you give to end users.
REM    - WITHOUT Inno Setup: dist\VideoCheckInstallerCore.exe
REM         Still fully functional (graphical progress window, no console),
REM         just without the Windows-installer chrome around it.
REM ─────────────────────────────────────────────────────────────
setlocal

python -m pip install --upgrade pyinstaller
if errorlevel 1 goto :error

REM --windowed: no console window at all — the installer shows its own
REM pywebview progress window instead (see bootstrap.py main_gui()).
REM --add-data "src;dest_inside_bundle" bundles the project files next to
REM bootstrap.py so it can copy them into the user's install folder.
python -m PyInstaller ^
    --onefile ^
    --windowed ^
    --name VideoCheckInstallerCore ^
    --hidden-import webview ^
    --hidden-import webview.platforms.winforms ^
    --hidden-import webview.platforms.edgechromium ^
    --collect-all webview ^
    --add-data "..\video_check.py;." ^
    --add-data "..\preinstall.py;." ^
    --add-data "..\pyproject.toml;." ^
    --add-data "..\dashboard.html;." ^
    --add-data "..\Makefile;." ^
    --add-data "..\src;src" ^
    bootstrap.py

if errorlevel 1 goto :error

echo.
echo  Core installer built: dist\VideoCheckInstallerCore.exe

REM Look for Inno Setup's command-line compiler on PATH or in its default
REM install locations, and wrap the core exe into a real installer wizard.
set ISCC=
where iscc.exe >nul 2>nul
if not errorlevel 1 (
    set ISCC=iscc.exe
) else if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" (
    set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
) else if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" (
    set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
)

if "%ISCC%"=="" (
    echo.
    echo  Inno Setup not found — skipping the final wizard-installer step.
    echo  Install it from https://jrsoftware.org/isdl.php ^(free, ~5MB^),
    echo  then either re-run this script, or open VideoCheck.iss and click
    echo  Compile.
    echo.
    echo  For now, dist\VideoCheckInstallerCore.exe already works standalone
    echo  ^(graphical progress window, no console^) — it just doesn't have
    echo  the Start Menu icon / Add-or-Remove-Programs entry that Inno adds.
    pause
    goto :eof
)

echo  Found Inno Setup — building the final wizard installer...
"%ISCC%" VideoCheck.iss
if errorlevel 1 goto :error

echo.
echo  Build complete: dist\VideoCheck-Setup.exe
echo  Give this single file to non-technical users — double-click, Next,
echo  Next, Finish.
pause
goto :eof

:error
echo.
echo  Build failed. See errors above.
pause
exit /b 1
