from pathlib import Path
import shutil
import subprocess


def test_whisper_cpp_vulkan_installer_conditions() -> None:
    script = Path("scripts/windows/install_whisper_cpp_vulkan.ps1").read_text(encoding="utf-8")

    assert "No Windows Vulkan zip asset found in latest release." in script
    assert "windows|win" in script
    assert "vulkan" in script
    assert "\\.zip$" in script

    # Must not require x64/amd64 in the base matching filter.
    assert "No Windows x64 Vulkan zip asset found in latest release." not in script

    assert "ggml-large-v3-turbo.bin" in script
    assert "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin?download=true" in script
    assert "CODEAGENT_FFMPEG_BIN" in script
    assert "codexffmpeg/releases/latest" in script


def test_wrapper_bat_calls_powershell_installer() -> None:
    wrapper = Path("setup_whisper_cpp_vulkan_windows.bat")
    assert wrapper.exists()
    content = wrapper.read_text(encoding="utf-8")
    assert "install_whisper_cpp_vulkan.ps1" in content
    assert "-ExecutionPolicy Bypass" in content


def test_whisper_cpp_vulkan_installer_powershell_parse() -> None:
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if powershell is None:
        import pytest

        pytest.skip("PowerShell is not available in this environment.")

    command = (
        "$tokens=$null;$errors=$null;"
        "[System.Management.Automation.Language.Parser]::ParseFile("
        "'scripts/windows/install_whisper_cpp_vulkan.ps1',[ref]$tokens,[ref]$errors"
        ") | Out-Null; "
        "if($errors.Count -gt 0){$errors | Format-List; exit 1}else{Write-Host 'PowerShell syntax OK'}"
    )
    subprocess.run(
        [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        check=True,
    )
