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
echo   Model startup is DB-managed
echo   If model_db exists, the recommended startup LLM will auto-load
echo.
set INITIAL_MODEL=
set STARTUP_PROFILE=auto
set PRIMARY_PORT=8080
goto :start_api

REM ==============================================
REM  MODE 2: QWEN35
REM ==============================================
:qwen35
echo.
echo [QWEN35 MODE]
echo   Startup preference selected, but actual load is DB-managed
echo.
set INITIAL_MODEL=
set STARTUP_PROFILE=qwen35
set PRIMARY_PORT=8080
goto :start_api

REM ==============================================
REM  MODE 3: CODER
REM ==============================================
:coder
echo.
echo [CODER MODE]
echo   Startup preference selected, but actual load is DB-managed
echo.
set INITIAL_MODEL=
set STARTUP_PROFILE=coder
set PRIMARY_PORT=8080
goto :start_api

REM ==============================================
REM  MODE 4: MISTRAL
REM ==============================================
:mistral
echo.
echo [MISTRAL MODE]
echo   Startup preference selected, but actual load is DB-managed
echo.
set INITIAL_MODEL=
set STARTUP_PROFILE=mistral
set PRIMARY_PORT=8080
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

set CODEAGENT_LLM_PLANNER=http://127.0.0.1:%PRIMARY_PORT%/v1/chat/completions
set CODEAGENT_LLM_EXECUTOR=http://127.0.0.1:%PRIMARY_PORT%/v1/chat/completions
set CODEAGENT_LLM_CHAT=http://127.0.0.1:%PRIMARY_PORT%/v1/chat/completions
set CODEAGENT_LLM_LIGHT=http://127.0.0.1:%PRIMARY_PORT%/v1/chat/completions
set CODEAGENT_LLM_MODE=%MODE%

echo.
echo [FastAPI] Starting CodeAgent on port 8000...
start /B "CodeAgent [8000]" python -m uvicorn main:app --host 0.0.0.0 --port 8000 --log-level info --app-dir "%~dp0"
echo Waiting for FastAPI on port 8000...
set /a API_WAIT_SEC=0
:wait_api
timeout /t 2 >nul
set /a API_WAIT_SEC+=2
for /f %%i in ('curl -s -o nul -w "%%{http_code}" http://127.0.0.1:8000/health 2^>nul') do set API_HTTP_CODE=%%i
if not "%API_HTTP_CODE%"=="200" (
    echo   FastAPI loading... %API_WAIT_SEC%s
    if %API_WAIT_SEC% GEQ 30 (
        echo [ERROR] FastAPI did not become ready.
        echo         If this is the first run and model_db.db does not exist, startup should skip DB restore.
        echo         Check the log above for any Python traceback.
        exit /b 1
    )
    goto :wait_api
)
echo [OK] FastAPI ready

echo.
echo Checking model database...
set MODEL_DB_EXISTS=
set MODEL_DB_TOTAL=
for /f "tokens=1,2 delims=|" %%a in ('python -c "import json,urllib.request; d=json.load(urllib.request.urlopen('http://127.0.0.1:8000/models/db/status')); print(str(1 if d.get('db_exists') else 0) + '|' + str(d.get('total', 0)))" 2^>nul') do (
    set MODEL_DB_EXISTS=%%a
    set MODEL_DB_TOTAL=%%b
)
if not "%MODEL_DB_EXISTS%"=="1" goto :skip_llm_wait
if "%MODEL_DB_TOTAL%"=="0" goto :skip_llm_wait

echo [ModelDB] Found %MODEL_DB_TOTAL% model(s). Requesting default LLM load...
curl -s -X POST http://127.0.0.1:8000/model/auto-load -H "Content-Type: application/json" -d "{\"reason\":\"start_bat\"}" >nul 2>&1

echo.
echo Waiting for LLM on port %PRIMARY_PORT%...
set /a WAIT_SEC=0
set HTTP_CODE=
:wait_loop
timeout /t 2 >nul
set /a WAIT_SEC+=2
for /f %%i in ('curl -s -o nul -w "%%{http_code}" http://127.0.0.1:%PRIMARY_PORT%/health 2^>nul') do set HTTP_CODE=%%i
if not "%HTTP_CODE%"=="200" (
    echo   LLM loading... %WAIT_SEC%s
    if %WAIT_SEC% GEQ 180 (
        echo [WARN] LLM is still not ready after %WAIT_SEC%s.
        echo        FastAPI is running, so open the UI and check server logs or model settings.
        goto :show
    )
    goto :wait_loop
)
echo [OK] LLM ready
goto :after_llm_wait

:skip_llm_wait
echo [WAIT] model_db is missing or empty. Skipping LLM startup wait.
echo        Run Models tab scan/add/benchmark first; FastAPI will auto-load after DB is created.

:after_llm_wait

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
echo   Mode  : %MODE%  Profile: %STARTUP_PROFILE%
echo ==============================================
echo.
echo [Launcher] Ready. Type 'exit' to close this window.
cmd /k
