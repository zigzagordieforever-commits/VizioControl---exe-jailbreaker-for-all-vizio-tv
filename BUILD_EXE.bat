@echo off
setlocal
cd /d "%~dp0"
echo === Building VizioControl.exe ===
where python >nul 2>nul
if errorlevel 1 (
  echo Python not found. Installing it with winget...
  winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
  echo.
  echo Python was installed. CLOSE this window and double-click BUILD_EXE.bat again.
  pause
  exit /b
)
python -m pip install --quiet --upgrade pyinstaller
if errorlevel 1 ( echo pip failed. Check your internet connection. & pause & exit /b 1 )
echo Installing optional extras (bleak, for the BLE Remote tab)...
python -m pip install --quiet --upgrade bleak
set "BLEAK_FLAGS="
python -c "import bleak" >nul 2>nul
if not errorlevel 1 (
  echo bleak OK - bundling it into the exe.
  set "BLEAK_FLAGS=--hidden-import bleak --hidden-import bleak.backends.winrt --collect-all bleak --collect-all winrt"
) else (
  echo bleak didn't install cleanly - building without it ^(BLE Remote tab will say to install it^).
)
copy /y vizio_control.pyw vizio_control_build.py >nul
python -m PyInstaller --onefile --windowed --name VizioControl --icon VizioControl.ico %BLEAK_FLAGS% vizio_control_build.py
del vizio_control_build.py >nul 2>nul
if exist dist\VizioControl.exe (
  copy /y dist\VizioControl.exe VizioControl.exe >nul
  echo.
  echo DONE! VizioControl.exe is in this folder. Double-click it to run.
) else (
  echo Build failed - see messages above.
)
pause
