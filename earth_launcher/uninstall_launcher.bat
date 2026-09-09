@echo off
setlocal

title URBANFLOW Google Earth Pro Launcher

echo.
echo ==========================================
echo   URBANFLOW Launcher Uninstaller
echo ==========================================
echo.

reg delete "HKCU\Software\Classes\urbanflow" /f >nul 2>&1

if errorlevel 1 (
    echo [INFO] Protocol registration was not found.
) else (
    echo [OK] URBANFLOW protocol removed.
)

set "INSTALL_DIR=%LOCALAPPDATA%\URBANFLOW\EarthLauncher"

if exist "%INSTALL_DIR%" (
    rmdir /S /Q "%INSTALL_DIR%"
    echo [OK] Launcher files removed.
) else (
    echo [INFO] Launcher files were not found.
)

echo.
echo Uninstallation completed.
echo.

pause
exit /b 0