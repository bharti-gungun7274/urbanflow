@echo off
setlocal

title URBANFLOW Google Earth Pro Launcher

echo.
echo ==========================================
echo   URBANFLOW Google Earth Pro Launcher
echo ==========================================
echo.

set "INSTALL_DIR=%LOCALAPPDATA%\URBANFLOW\EarthLauncher"

echo Installing to:
echo %INSTALL_DIR%
echo.

if not exist "%INSTALL_DIR%" (
    mkdir "%INSTALL_DIR%"
)

copy /Y "%~dp0URBANFLOW_Earth_Launcher.exe" "%INSTALL_DIR%\URBANFLOW_Earth_Launcher.exe" >nul

if errorlevel 1 (
    echo.
    echo [ERROR] Could not copy the launcher.
    echo.
    pause
    exit /b 1
)

echo [OK] Launcher copied successfully.
echo.

reg add "HKCU\Software\Classes\urbanflow" /ve /d "URL:URBANFLOW Protocol" /f >nul
reg add "HKCU\Software\Classes\urbanflow" /v "URL Protocol" /d "" /f >nul
reg add "HKCU\Software\Classes\urbanflow\shell\open\command" /ve /d "\"%INSTALL_DIR%\URBANFLOW_Earth_Launcher.exe\" \"%%1\"" /f >nul

if errorlevel 1 (
    echo.
    echo [ERROR] Could not register the URBANFLOW protocol.
    echo.
    pause
    exit /b 1
)

echo [OK] URBANFLOW protocol registered successfully.
echo.
echo ==========================================
echo Installation completed successfully.
echo ==========================================
echo.
echo You can now use:
echo.
echo OPEN IN GOOGLE EARTH PRO
echo.
pause
exit /b 0