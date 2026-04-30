@echo off
chcp 65001 >nul
setlocal
set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"
set PYTHONUTF8=1
set CODEAGENT_STYLE_BERT_VITS2_DEVICE=directml
python scripts\setup_style_bert_vits2_windows.py --with-directml
if not "%ERRORLEVEL%"=="0" (
    echo [ERROR] Style-Bert-VITS2 Windows setup failed.
    pause
    exit /b %ERRORLEVEL%
)
echo [OK] Style-Bert-VITS2 Windows setup completed.
pause
