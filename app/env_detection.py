from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def detect_runpod() -> bool:
    return bool(os.environ.get("RUNPOD_POD_ID") or os.environ.get("RUNPOD_API_KEY"))


def detect_os_profile() -> dict:
    profile = {
        "system": "",
        "os_name": "",
        "is_windows": False,
        "is_linux": False,
        "is_macos": False,
        "machine": "",
        "python_executable": "",
    }
    try:
        profile["system"] = platform.system() or ""
    except Exception:
        profile["system"] = ""
    try:
        profile["os_name"] = os.name or ""
    except Exception:
        profile["os_name"] = ""
    try:
        profile["machine"] = platform.machine() or ""
    except Exception:
        profile["machine"] = ""
    try:
        profile["python_executable"] = sys.executable or ""
    except Exception:
        profile["python_executable"] = ""

    system_lower = profile["system"].lower()
    profile["is_windows"] = system_lower == "windows"
    profile["is_linux"] = system_lower == "linux"
    profile["is_macos"] = system_lower == "darwin"
    return profile


def _run_command_text(cmd: list[str], timeout: int = 5) -> str:
    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return (completed.stdout or "").strip()
    except Exception:
        return ""


def _classify_gpu_vendor(names: list[str]) -> tuple[str, str]:
    cleaned = [n.strip() for n in names if (n or "").strip()]
    if not cleaned:
        return "none", ""

    def _matches(text: str, keys: tuple[str, ...]) -> bool:
        lower = text.lower()
        return any(k in lower for k in keys)

    priorities: list[tuple[str, tuple[str, ...]]] = [
        ("amd", ("amd", "radeon")),
        ("nvidia", ("nvidia", "geforce", "rtx", "cuda")),
        ("intel", ("intel", "arc", "iris", "uhd")),
        ("apple", ("apple", "m1", "m2", "m3", "m4")),
    ]
    for vendor, keys in priorities:
        for n in cleaned:
            if _matches(n, keys):
                return vendor, n
    return "unknown", cleaned[0]


def detect_gpu_profile() -> dict:
    profile = {
        "has_gpu": False,
        "vendor": "none",
        "name": "",
        "backend_candidates": ["cpu"],
        "recommended_tts_device": "cpu",
        "recommended_llama_backend": "cpu",
        "directml_candidate": False,
        "cuda_candidate": False,
        "rocm_candidate": False,
        "notes": [],
        "tested": {"windows": True, "cuda": False, "macos": False},
    }
    try:
        os_profile = detect_os_profile()
        system = (os_profile.get("system") or "").lower()
        machine = (os_profile.get("machine") or "").lower()
        runpod = detect_runpod()

        if system == "windows":
            out = _run_command_text([
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name",
            ])
            names = []
            for line in out.splitlines():
                text = line.strip()
                if not text:
                    continue
                if text.lower() == "microsoft basic display adapter":
                    continue
                names.append(text)
            vendor, name = _classify_gpu_vendor(names)
            profile["vendor"] = vendor
            profile["name"] = name
            profile["has_gpu"] = vendor not in {"none"}
            if vendor == "amd":
                profile.update(
                    {
                        "backend_candidates": ["directml", "vulkan", "cpu"],
                        "recommended_tts_device": "cpu",
                        "recommended_llama_backend": "vulkan",
                        "directml_candidate": True,
                        "cuda_candidate": False,
                        "rocm_candidate": False,
                    }
                )
                profile["notes"].append(
                    "Windows AMD detected; ROCm is not used. DirectML is experimental for Style-Bert-VITS2."
                )
            elif vendor == "nvidia":
                profile.update(
                    {
                        "backend_candidates": ["cuda", "directml", "cpu"],
                        "recommended_tts_device": "cuda",
                        "recommended_llama_backend": "cuda",
                        "cuda_candidate": True,
                        "directml_candidate": True,
                    }
                )
                profile["notes"].append(
                    "NVIDIA/CUDA path is detected but not validated in this Phase 1 change."
                )
            elif vendor == "intel":
                profile.update(
                    {
                        "backend_candidates": ["directml", "cpu"],
                        "recommended_tts_device": "cpu",
                        "recommended_llama_backend": "cpu",
                        "directml_candidate": True,
                    }
                )
            return profile

        if system == "darwin":
            profile["notes"].append("macOS/MPS path is a placeholder and not validated in this Phase 1 change.")
            if "arm" in machine or "aarch64" in machine:
                profile.update(
                    {
                        "vendor": "apple",
                        "name": "Apple Silicon",
                        "has_gpu": True,
                        "backend_candidates": ["mps", "cpu"],
                        "recommended_tts_device": "mps",
                    }
                )
            return profile

        nvidia_out = _run_command_text(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"])
        nvidia_names = [line.strip() for line in nvidia_out.splitlines() if line.strip()]
        has_rocm_candidate = Path("/dev/kfd").exists() or bool(shutil.which("rocminfo"))

        if nvidia_names:
            profile.update(
                {
                    "vendor": "nvidia",
                    "name": nvidia_names[0],
                    "has_gpu": True,
                    "cuda_candidate": True,
                }
            )
            if runpod:
                profile.update(
                    {
                        "backend_candidates": ["cuda", "cpu"],
                        "recommended_tts_device": "cuda",
                        "recommended_llama_backend": "cuda",
                    }
                )
                profile["notes"].append(
                    "Runpod/NVIDIA CUDA path retained for compatibility but not locally validated in this Phase 1 change."
                )
            return profile

        if has_rocm_candidate:
            profile.update(
                {
                    "vendor": "amd",
                    "has_gpu": True,
                    "backend_candidates": ["rocm", "cpu"],
                    "recommended_tts_device": "cpu",
                    "recommended_llama_backend": "cpu",
                    "rocm_candidate": True,
                }
            )
            profile["notes"].append(
                "Linux AMD ROCm candidate detected, but ROCm is not part of the Windows AMD local path."
            )
        return profile
    except Exception as e:
        profile["notes"].append(f"environment detection fallback: {e}")
        return profile
