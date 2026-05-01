@echo off
chcp 65001 >nul
setlocal

set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"
set SETUP_SCRIPT=%SCRIPT_DIR%scripts\setup_searxng_windows.py

if not exist "%SETUP_SCRIPT%" (
    echo [ERROR] SearXNG setup script not found: %SETUP_SCRIPT%
    pause
    exit /b 1
)

echo ==============================================
echo  CodeAgent SearXNG Setup ^(Windows^)
echo ==============================================
echo Running SearXNG setup...
python "%SETUP_SCRIPT%"
set EXIT_CODE=%ERRORLEVEL%

if not "%EXIT_CODE%"=="0" (
    echo [ERROR] SearXNG setup failed with code %EXIT_CODE%
    pause
)

exit /b %EXIT_CODE%
