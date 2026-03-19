@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
title CodeAgent Launcher

echo ==============================================
echo  CodeAgent  -  Auto Model Switcher
echo  GPU: RX9070XT 16GB   RAM: 32GB
echo ==============================================
echo.

REM --- Model paths ---
set MODEL_BASIC=E:\LLMs\models\lmstudio-community\gpt-oss-20b-GGUF\gpt-oss-20b-Q4_K_M.gguf
set MODEL_QWEN9B=E:\LLMs\unsloth\Qwen3.5-9B-GGUF\Qwen3.5-9B-Q4_K_S.gguf
set MODEL_ROUTER=E:\LLMs\models\lmstudio-community\LFM2.5-1.2B-Instruct-GGUF\LFM2.5-1.2B-Instruct-Q8_0.gguf
set MODEL_MISTRAL=E:\LLMs\unsloth\Mistral-Small-3.2-24B-Instruct-2506-GGUF\Mistral-Small-3.2-24B-Instruct-2506-Q3_K_S.gguf
set MODEL_GEMMA=E:\LLMs\models\lmstudio-community\gemma-3-12b-it-GGUF\gemma-3-12b-it-Q4_K_M.gguf
set MODEL_GPT_OSS=E:\LLMs\models\lmstudio-community\gpt-oss-20b-GGUF\gpt-oss-20b-Q4_K_M.gguf
set MODEL_QWEN35=E:\LLMs\lmstudio-community\Qwen3.5-35B-A3B-GGUF\Qwen3.5-35B-A3B-Q4_K_M.gguf
set MODEL_CODER=E:\LLMs\unsloth\Qwen3-Coder-Next-GGUF\Qwen3-Coder-Next-Q3_K_S.gguf

REM --- ModelManager settings ---
set LLAMA_SERVER_PATH=%~dp0llama\llama-server.exe
set LLM_PORT=8080
set INITIAL_MODEL=basic
set ROUTER_URL=

set LLAMA=%~dp0llama\llama-server.exe
set UI_SRC=%~dp0ui.html
set UI_DST=%~dp0ui\index.html

REM ==============================================
REM  Default AUTO: 2 sec key wait, press any key to select mode
REM ==============================================
set MODE=1
echo Starting in AUTO mode (GPT-OSS-20B basic, 154 tok/s)...
echo Press any key within 2 seconds to select mode manually.
echo.

REM 2choice /t 2 /d y /n
choice /t 2 /d y /n >nul 2>&1
if errorlevel 2 goto :select_mode
if errorlevel 1 goto :auto

REM ==============================================
REM  
REM ==============================================
:select_mode
echo.
echo ==============================================
echo  Startup Mode:
echo.
echo  1. AUTO    - GPT-OSS-20B (11.5GB, 154 tok/s) always-on
echo               Auto-switches to best model per task
echo               [Recommended]
echo.
echo  2. QWEN35  - Qwen3.5-35B (19.7GB, 28 tok/s)
echo               High quality code. No auto-switch.
echo.
echo  3. CODER   - Qwen3-Coder-Next (32.2GB, 13 tok/s)
echo               Best code quality. No auto-switch.
echo.
echo  4. MISTRAL - Mistral-Small-3.2-24B (11.2GB, 37 tok/s)
echo               JSON stable. No auto-switch.
echo ==============================================
set /p MODE="Mode [1-4] (default=1): "
if "%MODE%"=="" set MODE=1
if "%MODE%"=="2" goto :qwen35
if "%MODE%"=="3" goto :coder
if "%MODE%"=="4" goto :mistral
goto :auto

REM ==============================================
REM  MODE 1: AUTO - GPT-OSS-20B + ModelManager
REM ==============================================
:auto
set MODE=1
echo.
echo [AUTO MODE]
echo   Port 8080: GPT-OSS-20B  basic always-on  11.5GB VRAM  154 tok/s
echo   Auto-switch: code-Qwen35, complex-Coder, verify-Mistral
echo.
set INITIAL_MODEL=basic
set PRIMARY_PORT=8080

echo [1/1] Starting GPT-OSS-20B on port 8080...
start /B /D "%~dp0" "LLM-Basic [8080]" "%LLAMA%" --model "%MODEL_GPT_OSS%" --port 8080 --host 0.0.0.0 --ctx-size 16384 -ngl 999 --threads 8 --no-mmap --log-disable
goto :start_api

REM ==============================================
REM  MODE 2: QWEN35
REM ==============================================
:qwen35
echo.
echo [QWEN35 MODE]
echo   Port 8080: Qwen3.5-35B  19.7GB  28 tok/s  ctx=32768
echo.
set INITIAL_MODEL=qwen35
set PRIMARY_PORT=8080

echo [1/1] Starting Qwen3.5-35B on port 8080...
start /B /D "%~dp0" "LLM-Qwen35 [8080]" "%LLAMA%" --model "%MODEL_QWEN35%" --port 8080 --host 0.0.0.0 --ctx-size 32768 -ngl 999 --threads 12 --no-mmap --parallel 1 --batch-size 2048 --ubatch-size 64 --cache-type-k q8_0 --cache-type-v q8_0 --jinja --reasoning-budget 0 --log-disable
goto :start_api

REM ==============================================
REM  MODE 3: CODER
REM ==============================================
:coder
echo.
echo [CODER MODE]
echo   Port 8080: Qwen3-Coder-Next  32.2GB (VRAM16GB+RAM16GB)  ctx=32768
echo.
set INITIAL_MODEL=coder
set PRIMARY_PORT=8080

echo [1/1] Starting Qwen3-Coder-Next on port 8080...
start /B /D "%~dp0" "LLM-Coder [8080]" "%LLAMA%" --model "%MODEL_CODER%" --port 8080 --host 0.0.0.0 --ctx-size 32768 -ngl 31 --threads 12 --no-mmap --jinja --reasoning-budget 0 --log-disable
goto :start_api

REM ==============================================
REM  MODE 4: MISTRAL
REM ==============================================
:mistral
echo.
echo [MISTRAL MODE]
echo   Port 8080: Mistral-Small-3.2-24B  11.2GB  37 tok/s  ctx=8192
echo.
set INITIAL_MODEL=mistral
set PRIMARY_PORT=8080

echo [1/1] Starting Mistral-Small-3.2-24B on port 8080...
start /B /D "%~dp0" "LLM-Mistral [8080]" "%LLAMA%" --model "%MODEL_MISTRAL%" --port 8080 --host 0.0.0.0 --ctx-size 8192 -ngl 999 --threads 8 --no-mmap --log-disable
goto :start_api

REM ==============================================
REM  FastAPI backend
REM ==============================================
:start_api

if exist "%UI_SRC%" (
    if not exist "%~dp0ui" mkdir "%~dp0ui"
    copy /Y "%UI_SRC%" "%UI_DST%" >nul
    echo [UI] ui.html copied
)


echo.
echo Waiting for LLM on port %PRIMARY_PORT%...
set /a WAIT_SEC=0
:wait_loop
timeout /t 2 >nul
set /a WAIT_SEC+=2
for /f %%i in ('curl -s -o nul -w "%%{http_code}" http://127.0.0.1:%PRIMARY_PORT%/health 2^>nul') do set HTTP_CODE=%%i
if not "%HTTP_CODE%"=="200" (
    echo   Loading... %WAIT_SEC%s
    goto :wait_loop
)
echo [OK] LLM ready

set CODEAGENT_LLM_PLANNER=http://127.0.0.1:%PRIMARY_PORT%/v1/chat/completions
set CODEAGENT_LLM_EXECUTOR=http://127.0.0.1:%PRIMARY_PORT%/v1/chat/completions
set CODEAGENT_LLM_CHAT=http://127.0.0.1:%PRIMARY_PORT%/v1/chat/completions
set CODEAGENT_LLM_LIGHT=http://127.0.0.1:%PRIMARY_PORT%/v1/chat/completions
set CODEAGENT_LLM_MODE=%MODE%

echo.
echo [FastAPI] Starting CodeAgent on port 8000...
start /B "CodeAgent [8000]" python -m uvicorn main:app --host 0.0.0.0 --port 8000 --log-level info --app-dir "%~dp0"
timeout /t 3 >nul

for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /i "IPv4" ^| findstr /v "127.0.0.1"') do (
    set LAN_IP=%%a
    goto :show
)
:show
set LAN_IP=%LAN_IP: =%

echo.
echo ==============================================
echo  CodeAgent ready!
echo   Local : http://localhost:8000/
echo   LAN   : http://%LAN_IP%:8000/
echo   Mode  : %MODE%  Model: %INITIAL_MODEL%
echo ==============================================
echo.
echo [Launcher] Ready. Type 'exit' to close this window.
cmd /k
