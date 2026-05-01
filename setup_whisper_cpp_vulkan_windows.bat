@echo off
chcp 65001 >nul
setlocal

set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

echo ==============================================
echo  Setup whisper.cpp Vulkan for Windows AMD
echo ==============================================

powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%scripts\windows\install_whisper_cpp_vulkan.ps1" %*

set EXIT_CODE=%ERRORLEVEL%

if not "%EXIT_CODE%"=="0" (
    echo.
    echo [ERROR] whisper.cpp Vulkan setup failed with code %EXIT_CODE%
    pause
    exit /b %EXIT_CODE%
)

echo.
echo [OK] whisper.cpp Vulkan setup completed.
echo.
pause
exit /b 0
