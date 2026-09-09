@echo off
setlocal

for %%I in ("%~dp0..\dist\URBANFLOW_Earth_Launcher.exe") do set "LAUNCHER=%%~fI"

if not exist "%LAUNCHER%" (
    echo.
    echo ERROR: URBANFLOW_Earth_Launcher.exe was not found.
    echo.
    echo Expected:
    echo %LAUNCHER%
    echo.
    pause
    exit /b 1
)

echo Registering URBANFLOW Earth Launcher...
echo.
echo Launcher:
echo %LAUNCHER%
echo.

reg add "HKCU\Software\Classes\urbanflow" /ve /d "URL:URBANFLOW Protocol" /f >nul
reg add "HKCU\Software\Classes\urbanflow" /v "URL Protocol" /d "" /f >nul
reg add "HKCU\Software\Classes\urbanflow\shell\open\command" /ve /d "\"%LAUNCHER%\" \"%%1\"" /f >nul

if errorlevel 1 (
    echo.
    echo ERROR: Protocol registration failed.
    echo.
    pause
    exit /b 1
)

echo.
echo ==========================================
echo URBANFLOW protocol registered successfully
echo ==========================================
echo.
echo Registered launcher:
echo %LAUNCHER%
echo.
pause