param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"

function Invoke-DownloadWithRetry {
    param(
        [Parameter(Mandatory = $true)][string]$Uri,
        [Parameter(Mandatory = $true)][string]$OutFile,
        [int]$MaxRetries = 3
    )

    for ($attempt = 1; $attempt -le $MaxRetries; $attempt++) {
        try {
            Invoke-WebRequest -Uri $Uri -OutFile $OutFile -Headers @{ "User-Agent" = "CodeAgentPersonal" }
            return
        } catch {
            if ($attempt -eq $MaxRetries) {
                throw
            }
            Write-Host "[download] attempt ${attempt}/${MaxRetries} failed. retrying..."
            Start-Sleep -Seconds ([Math]::Min(2 * $attempt, 10))
        }
    }
}

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

        $matchingAssets = $release.assets |
            Where-Object {
                $_.name -match "(?i)(windows|win)" -and
                $_.name -match "(?i)vulkan" -and
                $_.name -match "(?i)\.zip$"
            }

        $asset = $matchingAssets |
            Sort-Object -Property @{ Expression = { if ($_.name -match "(?i)(x64|amd64|amd)") { 0 } else { 1 } } }, @{ Expression = { $_.name } } |
            Select-Object -First 1

        if (-not $asset) {
            Write-Host "[whisper.cpp] matching asset not found. Vulkan zip candidates:"
            $release.assets |
                Where-Object { $_.name -match "(?i)vulkan" -and $_.name -match "\.zip$" } |
                ForEach-Object { Write-Host " - $($_.name)" }
            throw "No Windows Vulkan zip asset found in latest release."
        }

        if ($Force -and (Test-Path $InstallDir)) {
            Remove-Item -Recurse -Force $InstallDir
            New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
        }

        $zipPath = Join-Path $env:TEMP $asset.name
        Write-Host "[whisper.cpp] downloading: $($asset.name)"
        Invoke-DownloadWithRetry -Uri $asset.browser_download_url -OutFile $zipPath

        Expand-Archive -Path $zipPath -DestinationPath $InstallDir -Force
    }

    $bins = Get-ChildItem $InstallDir -Recurse -Include "whisper-cli.exe","main.exe","whisper.exe" -ErrorAction SilentlyContinue
    if (-not $bins) {
        throw "whisper.cpp executable not found under $InstallDir"
    }

    Write-Host "[whisper.cpp] detected executables:"
    foreach ($candidate in $bins) {
        Write-Host " - $($candidate.FullName)"
    }

    $bin = $bins | Select-Object -First 1

    Write-Host "[whisper.cpp] startup check: $($bin.FullName)"
    try {
        & $bin.FullName --help | Select-Object -First 20
    } catch {
        & $bin.FullName -h | Select-Object -First 20
    }

    $model = Join-Path $ModelDir "ggml-large-v3-turbo.bin"
    $modelPart = "${model}.part"
    $modelUrl = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin?download=true"
    $minModelBytes = 1GB

    $needModelDownload = $Force
    if (-not $needModelDownload) {
        if (-not (Test-Path $model)) {
            $needModelDownload = $true
        } else {
            $modelFile = Get-Item $model
            if ($modelFile.Length -lt $minModelBytes) {
                Write-Host "[whisper.cpp] existing model is smaller than 1GB. re-downloading."
                $needModelDownload = $true
            }
        }
    }

    if ($needModelDownload) {
        try {
            if (Test-Path $modelPart) {
                Remove-Item -Force $modelPart
            }
            Write-Host "[whisper.cpp] downloading model..."
            Write-Host "[whisper.cpp] source: $modelUrl"
            Invoke-DownloadWithRetry -Uri $modelUrl -OutFile $modelPart

            $partFile = Get-Item $modelPart
            if ($partFile.Length -lt $minModelBytes) {
                throw "Downloaded model is smaller than 1GB. It may be an HTML error page or incomplete download."
            }

            Move-Item -Force $modelPart $model
            Write-Host "[whisper.cpp] model saved: $model"
        } catch {
            Write-Host "[ERROR] Failed to download ggml-large-v3-turbo.bin"
            Write-Host "  target: $model"
            Write-Host "  manual: $modelUrl"
            throw
        }
    } else {
        Write-Host "[whisper.cpp] model already exists and is >=1GB: $model"
    }

    Write-Host ""
    Write-Host "Set these environment variables for Windows AMD Vulkan ASR:"
    Write-Host "set CODEAGENT_ASR_ENGINE=whisper_cpp"
    Write-Host "set CODEAGENT_WHISPER_CPP_BACKEND=vulkan"
    Write-Host "set CODEAGENT_WHISPER_CPP_BIN=$($bin.FullName)"
    Write-Host "set CODEAGENT_WHISPER_CPP_MODEL=$model"

    $ffmpegCmd = Get-Command ffmpeg -ErrorAction SilentlyContinue
    if (-not $ffmpegCmd) {
        Write-Host ""
        Write-Host "[WARN] ffmpeg is not found in PATH."
        Write-Host "       ffmpeg is required when using browser-recorded webm input."
        Write-Host "       If you only use wav input, ffmpeg is optional."
    } else {
        Write-Host ""
        Write-Host ("[whisper.cpp] ffmpeg found: " + $ffmpegCmd.Source)
    }
} catch {
    $msg = $_.Exception.Message
    Write-Error ("[whisper.cpp] install failed: " + $msg)
    exit 1
}
