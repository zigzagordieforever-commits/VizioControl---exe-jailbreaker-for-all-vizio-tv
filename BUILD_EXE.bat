@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "ROOT=%~dp0"
set "TEMP_ROOT=%ROOT%.build_tmp"
set "RELEASE_DIR=%ROOT%Release Candidate"
set "BUILT_EXE=%TEMP_ROOT%\dist\VizioControl.exe"
set "FINAL_EXE=%RELEASE_DIR%\VizioControl.exe"

echo ============================================================
echo VizioControl 1.7.2-rc1 - Windows EXE Builder
echo ============================================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo ERROR: Python was not found.
    echo Install Python 3.12 or newer from https://www.python.org/downloads/windows/
    echo Make sure "Add Python to PATH" is checked, then run this file again.
    pause
    exit /b 1
)

python -c "import sys; print('Python:', sys.version); raise SystemExit(0 if sys.version_info >= (3,12) else 1)"
if errorlevel 1 (
    echo ERROR: Python 3.12 or newer is required.
    pause
    exit /b 1
)

if not exist "%ROOT%vizio_control.pyw" (
    echo ERROR: vizio_control.pyw is missing. Extract the full project ZIP first.
    pause
    exit /b 1
)
if not exist "%ROOT%VizioControl.ico" (
    echo ERROR: VizioControl.ico is missing.
    pause
    exit /b 1
)

if exist "%TEMP_ROOT%" rmdir /s /q "%TEMP_ROOT%"
mkdir "%TEMP_ROOT%"
if errorlevel 1 (
    echo ERROR: Could not create temporary build folder.
    pause
    exit /b 1
)

echo [1/3] Installing build tools...
python -m pip install --upgrade pip
if errorlevel 1 goto :failed
python -m pip install -r "%ROOT%requirements-build.txt"
if errorlevel 1 goto :failed

echo.
echo [2/3] Building the single-file EXE...
python -m PyInstaller --noconfirm --clean --onefile --windowed --name VizioControl --icon "%ROOT%VizioControl.ico" --distpath "%TEMP_ROOT%\dist" --workpath "%TEMP_ROOT%\work" --specpath "%TEMP_ROOT%\spec" --collect-all sounddevice --collect-all dxcam --collect-all numpy --collect-all cv2 --collect-all PIL "%ROOT%vizio_control.pyw"
if errorlevel 1 goto :failed

if not exist "%BUILT_EXE%" (
    echo ERROR: PyInstaller finished but the EXE was not found.
    goto :failed
)
for %%F in ("%BUILT_EXE%") do if %%~zF LEQ 0 (
    echo ERROR: The EXE is empty.
    goto :failed
)

echo.
echo [3/3] Copying the finished EXE and cleaning temporary files...
if not exist "%RELEASE_DIR%" mkdir "%RELEASE_DIR%"
copy /y "%BUILT_EXE%" "%FINAL_EXE%" >nul
if errorlevel 1 goto :failed

REM The Release Candidate folder is intentionally kept clean: only the EXE remains.
for %%F in ("%RELEASE_DIR%\*") do (
    if /I not "%%~fF"=="%FINAL_EXE%" del /f /q "%%~fF" >nul 2>nul
)
for /d %%D in ("%RELEASE_DIR%\*") do rmdir /s /q "%%~fD" >nul 2>nul

rmdir /s /q "%TEMP_ROOT%" >nul 2>nul
if exist "%ROOT%__pycache%" rmdir /s /q "%ROOT%__pycache%" >nul 2>nul

 echo.
echo BUILD COMPLETE!
echo Your release file is:
echo %FINAL_EXE%
echo.
echo The temporary build folder was removed. Your source code and documentation were kept.
echo Test the EXE on your own PC before uploading it to GitHub Releases.
echo.
pause
exit /b 0

:failed
echo.
echo BUILD FAILED. The old EXE, if there was one, was not intentionally removed.
echo Temporary files are in:
echo %TEMP_ROOT%
echo Read the error above, fix it, then run BUILD_EXE.bat again.
echo.
pause
exit /b 1
