param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"

try {
    $RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
    $InstallDir = Join-Path $RepoRoot "ca_data\bin\whisper.cpp-vulkan"
    $ModelDir = Join-Path $RepoRoot "ca_data\asr_models\whisper_cpp"
    $ApiUrl = "https://api.github.com/repos/souten-yd/whisper.cpp/releases/latest"

    New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
    New-Item -ItemType Directory -Force -Path $ModelDir | Out-Null

    $installedBin = Get-ChildItem $InstallDir -Recurse -Include "whisper-cli.exe","main.exe","whisper.exe" -ErrorAction SilentlyContinue | Select-Object -First 1

    if ($installedBin -and -not $Force) {
        Write-Host "[whisper.cpp] already installed: $InstallDir"
    } else {
        Write-Host "[whisper.cpp] fetching latest release..."
        $release = Invoke-RestMethod -Uri $ApiUrl -Headers @{ "User-Agent" = "CodeAgentPersonal" }

        $asset = $release.assets |
            Where-Object {
                $_.name -match "(?i)(windows|win)" -and
                $_.name -match "(?i)vulkan" -and
                $_.name -match "(?i)(x64|amd64)" -and
                $_.name -match "\.zip$"
            } |
            Select-Object -First 1

        if (-not $asset) {
            Write-Host "[whisper.cpp] matching asset not found. Vulkan zip candidates:"
            $release.assets |
                Where-Object { $_.name -match "(?i)vulkan" -and $_.name -match "\.zip$" } |
                ForEach-Object { Write-Host " - $($_.name)" }
            throw "No Windows x64 Vulkan zip asset found in latest release."
        }

        if ($Force -and (Test-Path $InstallDir)) {
            Remove-Item -Recurse -Force $InstallDir
            New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
        }

        $zipPath = Join-Path $env:TEMP $asset.name
        Write-Host "[whisper.cpp] downloading: $($asset.name)"
        Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zipPath -Headers @{ "User-Agent" = "CodeAgentPersonal" }

        Expand-Archive -Path $zipPath -DestinationPath $InstallDir -Force
    }

    $bin = Get-ChildItem $InstallDir -Recurse -Include "whisper-cli.exe","main.exe","whisper.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $bin) {
        throw "whisper.cpp executable not found under $InstallDir"
    }

    Write-Host "[whisper.cpp] executable: $($bin.FullName)"
    try {
        & $bin.FullName --help | Select-Object -First 20
    } catch {
        & $bin.FullName -h | Select-Object -First 20
    }

    $model = Join-Path $ModelDir "ggml-large-v3-turbo.bin"

    Write-Host ""
    Write-Host "Set these environment variables for Windows AMD Vulkan ASR:"
    Write-Host "set CODEAGENT_ASR_ENGINE=whisper_cpp"
    Write-Host "set CODEAGENT_WHISPER_CPP_BACKEND=vulkan"
    Write-Host "set CODEAGENT_WHISPER_CPP_BIN=$($bin.FullName)"
    Write-Host "set CODEAGENT_WHISPER_CPP_MODEL=$model"

    if (-not (Test-Path $model)) {
        Write-Host ""
        Write-Host "[WARN] whisper.cpp ggml model is not found:"
        Write-Host "  $model"
        Write-Host "Place ggml-large-v3-turbo.bin there before using whisper.cpp ASR."
    }
} catch {
    Write-Error "[whisper.cpp] install failed: $($_.Exception.Message)"
    exit 1
}
