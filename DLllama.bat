@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

set "WORKDIR=%~dp0"
set "OUTDIR=%WORKDIR%llama"
set "ZIPFILE=%WORKDIR%llama-latest.zip"
set "TMPPS1=%TEMP%\get_llama_asset_url.ps1"

if exist "%OUTDIR%" (
    echo Remove existing llama folder...
    rmdir /s /q "%OUTDIR%"
)

echo.
echo Select backend:
echo   1 ^) Vulkan
echo   2 ^) HIP
echo   3 ^) CUDA
echo.

choice /c 123 /n /m "Enter 1, 2, or 3: "
set "SEL=%ERRORLEVEL%"

if "%SEL%"=="1" (
    set "BACKEND=Vulkan"
    set "PATTERN=.*win.*vulkan.*x64.*\.zip$"
)
if "%SEL%"=="2" (
    set "BACKEND=HIP"
    set "PATTERN=.*win.*hip.*x64.*\.zip$"
)
if "%SEL%"=="3" (
    set "BACKEND=CUDA"
    set "PATTERN=.*win.*cuda.*x64.*\.zip$"
)

echo.
echo Selected: %BACKEND%
echo [1/4] Get latest Windows %BACKEND% zip URL...

> "%TMPPS1%" echo $ProgressPreference = 'SilentlyContinue'
>>"%TMPPS1%" echo [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
>>"%TMPPS1%" echo $url = 'https://github.com/ggml-org/llama.cpp/releases/latest'
>>"%TMPPS1%" echo $pattern = '%PATTERN%'
>>"%TMPPS1%" echo $r = Invoke-WebRequest -UseBasicParsing -Uri $url -Headers @{ 'User-Agent'='Mozilla/5.0' }
>>"%TMPPS1%" echo $links = $r.Links ^| Where-Object { $_.href -match '/ggml-org/llama\.cpp/releases/download/.*/' + $pattern }
>>"%TMPPS1%" echo if (-not $links) { throw 'Requested Windows x64 zip was not found.' }
>>"%TMPPS1%" echo $href = $links[0].href
>>"%TMPPS1%" echo if ($href -notmatch '^https://') { $href = 'https://github.com' + $href }
>>"%TMPPS1%" echo Write-Output $href

for /f "usebackq delims=" %%I in (`powershell -NoProfile -ExecutionPolicy Bypass -File "%TMPPS1%"`) do (
    set "DOWNLOAD_URL=%%I"
)

del /f /q "%TMPPS1%" >nul 2>nul

if not defined DOWNLOAD_URL (
    echo [ERROR] Failed to get download URL.
    exit /b 1
)

echo [2/4] URL:
echo %DOWNLOAD_URL%

if exist "%ZIPFILE%" del /f /q "%ZIPFILE%"

echo [3/4] Download zip...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$ProgressPreference='SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -UseBasicParsing -Uri '%DOWNLOAD_URL%' -OutFile '%ZIPFILE%' -Headers @{ 'User-Agent'='Mozilla/5.0' }"

if errorlevel 1 (
    echo [ERROR] Download failed.
    exit /b 1
)

mkdir "%OUTDIR%" >nul 2>&1

echo [4/4] Extract zip...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "Expand-Archive -Path '%ZIPFILE%' -DestinationPath '%OUTDIR%' -Force"

if errorlevel 1 (
    echo [ERROR] Extract failed.
    exit /b 1
)

if exist "%ZIPFILE%" del /f /q "%ZIPFILE%"

echo.
echo Done.
echo Backend: %BACKEND%
echo Folder : %OUTDIR%
exit /b 0