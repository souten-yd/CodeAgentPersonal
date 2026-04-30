@echo off
chcp 65001 >nul
setlocal

REM Windows launcher wrapper
REM Core startup logic is implemented in Python for Runpod/Linux reuse.

set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"
set PY_LAUNCHER=%SCRIPT_DIR%scripts\start_codeagent.py

if not exist "%PY_LAUNCHER%" (
    echo [ERROR] Launcher not found: %PY_LAUNCHER%
    exit /b 1
)

echo ==============================================
echo  CodeAgent Launcher (Windows wrapper)
echo ==============================================

echo Starting Python launcher...
python "%PY_LAUNCHER%"
set EXIT_CODE=%ERRORLEVEL%

if not "%EXIT_CODE%"=="0" (
    echo [ERROR] Launcher exited with code %EXIT_CODE%
    pause
)

exit /b %EXIT_CODE%
