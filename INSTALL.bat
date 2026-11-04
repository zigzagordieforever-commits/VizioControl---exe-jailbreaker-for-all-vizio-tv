@echo off
setlocal
cd /d "%~dp0"
net session >nul 2>nul
if %errorlevel% neq 0 (
  echo Needs administrator rights ^(to install into Program Files^) - relaunching elevated...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -WorkingDirectory '%~dp0' -Verb RunAs"
  exit /b
)
echo === Installing Vizio Control ===
if not exist VizioControl.exe (
  if not exist vizio_control.pyw (
    echo Can't find VizioControl.exe or vizio_control.pyw next to this installer.
    pause & exit /b 1
  )
  echo No VizioControl.exe here yet - building it first ^(needs internet once^)...
  call BUILD_EXE.bat
  if not exist VizioControl.exe ( echo Build failed - see messages above. & pause & exit /b 1 )
)
set "DEST=%ProgramFiles%\VizioControl"
mkdir "%DEST%" >nul 2>nul
copy /y VizioControl.exe "%DEST%\" >nul
if exist VizioControl.ico copy /y VizioControl.ico "%DEST%\" >nul
if exist README.txt copy /y README.txt "%DEST%\" >nul

echo Creating Start Menu and Desktop shortcuts...
set "SM=%ProgramData%\Microsoft\Windows\Start Menu\Programs\VizioControl.lnk"
set "DT=%Public%\Desktop\VizioControl.lnk"
powershell -NoProfile -Command ^
  "$s=(New-Object -COM WScript.Shell).CreateShortcut('%SM%');" ^
  "$s.TargetPath='%DEST%\VizioControl.exe';$s.WorkingDirectory='%DEST%';$s.IconLocation='%DEST%\VizioControl.ico';$s.Save();" ^
  "$s=(New-Object -COM WScript.Shell).CreateShortcut('%DT%');" ^
  "$s.TargetPath='%DEST%\VizioControl.exe';$s.WorkingDirectory='%DEST%';$s.IconLocation='%DEST%\VizioControl.ico';$s.Save()"

echo Writing uninstaller and Add/Remove Programs entry...
> "%DEST%\UNINSTALL.bat" (
  echo @echo off
  echo del "%%ProgramData%%\Microsoft\Windows\Start Menu\Programs\VizioControl.lnk" 2^>nul
  echo del "%%Public%%\Desktop\VizioControl.lnk" 2^>nul
  echo reg delete "HKLM\Software\Microsoft\Windows\CurrentVersion\Uninstall\VizioControl" /f 2^>nul
  echo rmdir /s /q "%DEST%"
)
reg add "HKLM\Software\Microsoft\Windows\CurrentVersion\Uninstall\VizioControl" /v DisplayName /t REG_SZ /d "Vizio Control" /f >nul
reg add "HKLM\Software\Microsoft\Windows\CurrentVersion\Uninstall\VizioControl" /v DisplayIcon /t REG_SZ /d "%DEST%\VizioControl.ico" /f >nul
reg add "HKLM\Software\Microsoft\Windows\CurrentVersion\Uninstall\VizioControl" /v UninstallString /t REG_SZ /d "\"%DEST%\UNINSTALL.bat\"" /f >nul
reg add "HKLM\Software\Microsoft\Windows\CurrentVersion\Uninstall\VizioControl" /v Publisher /t REG_SZ /d "VizioControl" /f >nul

echo.
echo DONE. Installed to "%DEST%". Launch it from the Start Menu or Desktop.
echo Your settings/plugins still live in %%APPDATA%%\VizioControl ^(unchanged by install/uninstall^).
echo To remove later: Settings ^> Apps ^> Vizio Control ^> Uninstall, or run "%DEST%\UNINSTALL.bat".
pause
