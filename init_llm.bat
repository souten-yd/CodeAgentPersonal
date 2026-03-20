@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
title CodeAgent - LLM Database Initializer

echo ==============================================
echo  CodeAgent LLM Database Initializer
echo  benchmark_mem.py を使ってGGUFモデルをスキャン・
echo  ベンチマーク実行し model_db.db に登録します
echo ==============================================
echo.

REM --- 設定 ---
set SCRIPT_DIR=%~dp0
set PYTHON=python
set BENCH_SCRIPT=%SCRIPT_DIR%benchmark_mem.py

REM --- モデルフォルダ指定 (デフォルト: E:\LLMs) ---
if "%1"=="" (
    set MODEL_FOLDER=E:\LLMs
) else (
    set MODEL_FOLDER=%1
)

echo [1] モデルフォルダをスキャン: %MODEL_FOLDER%
echo     （全サブフォルダの .gguf ファイルを検索します）
echo.

REM --- CodeAgent APIを通じてスキャン ---
echo [2] CodeAgent API経由でDBに登録...
for /f "delims=" %%i in ('curl -s -X POST http://127.0.0.1:8000/models/db/scan ^
  -H "Content-Type: application/json" ^
  -d "{\"folder\":\"%MODEL_FOLDER%\"}" 2^>nul') do set SCAN_RESULT=%%i

if "!SCAN_RESULT!"=="" (
    echo [WARN] CodeAgent APIに接続できません。
    echo        start.bat でCodeAgentを先に起動してください。
    echo.
    echo [代替] benchmark_mem.py を直接実行します...
    echo.
    %PYTHON% "%BENCH_SCRIPT%"
    goto :done
)

echo [OK] スキャン結果: !SCAN_RESULT!
echo.

REM --- DBステータス確認 ---
echo [3] DBステータス確認...
for /f "delims=" %%i in ('curl -s http://127.0.0.1:8000/models/db/status 2^>nul') do set DB_STATUS=%%i
echo     %DB_STATUS%
echo.

echo ==============================================
echo  初期化完了！
echo  UIの "Models" タブでモデル一覧を確認できます。
echo  各モデルの "Bench" ボタンで性能計測が実行できます。
echo ==============================================
echo.

:done
echo [完了] このウィンドウを閉じてください。
pause
