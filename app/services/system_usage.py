"""System usage collection service and explicit dependency ports.

This module owns the live ``collect_system_usage_info()`` implementation while
keeping settings persistence and diagnostics publication behind
``UsageCollectorPorts``. It must stay free of imports from ``main``, settings
helpers, and diagnostics globals so importing it has no runtime collection side
effects; subprocess and GPU probes run only when collection is requested.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import json
import os
import platform
import re
import shutil
import subprocess
import threading
import time
from typing import Any, Mapping, Protocol, runtime_checkable


def _parse_int_maybe(value: Any) -> int:
    """Parse a comma-formatted non-negative integer, returning ``-1`` on failure."""
    text = str(value or "").strip().replace(",", "")
    return int(text) if text.isdigit() else -1


def _bytes_to_mb(value: Any) -> int:
    """Convert a byte count to whole MiB, returning ``-1`` for non-numeric input."""
    if not isinstance(value, (int, float)):
        return -1
    return int(value / (1024 * 1024))


def _kb_to_mb(value: Any) -> int:
    """Convert a KiB count to whole MiB, returning ``-1`` for non-numeric input."""
    if not isinstance(value, (int, float)):
        return -1
    return int(value / 1024)


def _calculate_percent(used: int | float, total: int | float) -> float:
    """Return a usage percentage or ``-1.0`` when the ratio is not meaningful."""
    if used >= 0 and total > 0:
        return (used / total) * 100.0
    return -1.0


def _usage_updated_at() -> str:
    """Return the usage payload timestamp in the existing ISO-8601 shape."""
    return datetime.now().isoformat()


def _gpu_util_nvidia_smi(timeout_sec: float) -> float | None:
    """Max GPU utilisation via a single nvidia-smi query, or None. The runpod-preferred probe."""
    if not shutil.which("nvidia-smi"):
        return None
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=timeout_sec)
        vals = [
            float(re.sub(r"[^0-9.]", "", ln) or -1)
            for ln in (r.stdout or "").splitlines() if ln.strip()
        ]
        vals = [v for v in vals if v >= 0]
        return max(vals) if vals else None
    except Exception:  # noqa: BLE001 - probe is advisory.
        return None


def _gpu_util_resource_monitor() -> float | None:
    """Max GPU utilisation via the full /system/usage resource monitor (Windows PDH + nvidia/AMD
    shapes), or None. The Windows-preferred probe."""
    try:
        ports = UsageCollectorPorts(settings=_NoopSettingsPort(), diagnostics=InMemoryUsageDiagnostics())
        payload = collect_system_usage_info(ports=ports)
        utils = [
            float(g.get("util_percent"))
            for g in (payload.get("gpus") or [])
            if isinstance(g, dict) and isinstance(g.get("util_percent"), (int, float)) and float(g.get("util_percent")) >= 0
        ]
        return max(utils) if utils else None
    except Exception:  # noqa: BLE001 - probe is advisory.
        return None


def sample_gpu_utilization(*, timeout_sec: float = 4.0) -> float | None:
    """Best-effort CURRENT GPU utilisation percent (max across GPUs), or ``None`` when no GPU /
    no probe is available.

    Lightweight companion to ``collect_system_usage_info`` for liveness checks (e.g. "is the model
    still computing during a long prefill / reasoning phase?"). The probe ORDER is chosen by
    environment detection — the same startup detection the rest of the app uses — because runpod and
    Windows expose GPU stats through different mechanisms:
      - runpod (Linux + NVIDIA): nvidia-smi utilisation query first.
      - Windows: the resource monitor (Task-Manager PDH / vendor CSV) first.
    The other probe is always tried as a fallback. Never raises — returns ``None`` so callers degrade
    to time-only liveness."""
    try:
        from app.env_detection import detect_os_profile, detect_runpod

        prefer_nvidia = bool(detect_runpod()) or not bool(detect_os_profile().get("is_windows"))
    except Exception:  # noqa: BLE001 - detection is advisory; default to nvidia-first.
        prefer_nvidia = True

    probes = (
        (_gpu_util_nvidia_smi(timeout_sec), _gpu_util_resource_monitor)
        if prefer_nvidia
        else (_gpu_util_resource_monitor(), lambda: _gpu_util_nvidia_smi(timeout_sec))
    )
    primary, secondary = probes
    if primary is not None:
        return primary
    return secondary()


class _NoopSettingsPort:
    """Minimal SettingsPort for standalone GPU sampling (no persisted settings needed)."""

    def get_setting(self, key: str) -> str | None:
        return None

    def set_setting(self, key: str, value: str) -> None:
        return None


def _normalize_static_gpu_usage(gpu: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize a static GPU probe row into the ``/system/usage`` GPU shape."""
    return {
        "name": gpu.get("name", "GPU"),
        "util_percent": -1,
        "vram_used_mb": -1,
        "vram_total_mb": gpu.get("memory_total_mb", -1),
        "vram_percent": -1,
    }


class SettingsPort(Protocol):
    """Settings persistence dependency used by usage collection."""

    def get_setting(self, key: str) -> str | None:
        """Return a setting value for ``key`` or ``None`` when unset."""
        ...

    def set_setting(self, key: str, value: str) -> None:
        """Persist a setting value for ``key``."""
        ...


@runtime_checkable
class UsageDiagnosticsPort(Protocol):
    """Diagnostics dependency used by usage collection and debug payloads."""

    def set_last_usage_diag(self, diag: dict[str, Any]) -> None:
        """Store the latest usage diagnostics payload."""
        ...

    def get_last_usage_diag(self) -> dict[str, Any]:
        """Return a copy or snapshot of the latest usage diagnostics payload."""
        ...


@dataclass(slots=True)
class InMemoryUsageDiagnostics:
    """Side-effect-free in-memory diagnostics adapter skeleton.

    This adapter is intentionally disconnected from ``main`` diagnostics globals.
    It exists as a small implementation candidate for the future usage
    collection service boundary.
    """

    _diag: dict[str, Any] = field(default_factory=dict)

    def set_last_usage_diag(self, diag: dict[str, Any]) -> None:
        """Store a shallow copy of the latest usage diagnostics payload."""
        self._diag = dict(diag)

    def get_last_usage_diag(self) -> dict[str, Any]:
        """Return a shallow copy of the latest usage diagnostics payload."""
        return dict(self._diag)


@dataclass(frozen=True, slots=True)
class UsageCollectorPorts:
    """Container for dependencies needed by the future usage collector."""

    settings: SettingsPort
    diagnostics: UsageDiagnosticsPort

_usage_diag_lock = threading.Lock()
_windows_dxdiag_cache: dict[str, Any] = {"mb": -1, "checked_at": 0.0}


def _read_meminfo_kb() -> tuple[int, int]:
    total_kb = 0
    avail_kb = 0
    try:
        if os.path.exists("/proc/meminfo"):
            with open("/proc/meminfo", "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        total_kb = int(line.split()[1])
                    elif line.startswith("MemAvailable:"):
                        avail_kb = int(line.split()[1])
            return total_kb, avail_kb
    except Exception:
        pass
    return 0, 0


def _probe_gpu_static(backend: str) -> list[dict]:
    gpus: list[dict] = []
    if backend == "nvidia-smi":
        for cmd in [
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.free", "--format=csv,noheader,nounits"],  # 1
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.used", "--format=csv,noheader,nounits"],  # 2
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],              # 3
            ["nvidia-smi", "-L"],                                                                           # 4
            ["nvidia-smi", "dmon", "-s", "m", "-c", "1"],                                                  # 5
        ]:
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
                for line in (r.stdout or "").splitlines():
                    parts = [x.strip() for x in line.split(",")]
                    if len(parts) >= 3:
                        total = _parse_int_maybe(parts[1]); x3 = _parse_int_maybe(parts[2])
                        if total > 0:
                            free = x3 if "free" in " ".join(cmd) else (max(0, total - max(0, x3)) if x3 >= 0 else -1)
                            gpus.append({"name": parts[0], "memory_total_mb": total, "memory_free_mb": free})
                    elif cmd[-1] == "-L" and "GPU " in line:
                        gpus.append({"name": line.strip(), "memory_total_mb": -1, "memory_free_mb": -1})
                if gpus:
                    break
            except Exception:
                continue
    elif backend == "rocm-smi":
        # 5 strategies: rocm-smi json/text/alt json + rocminfo + rocm_agent_enumerator
        try:
            r = subprocess.run(["rocm-smi", "--showproductname", "--showmeminfo", "vram", "--json"], capture_output=True, text=True, timeout=8)
            if r.returncode == 0 and (r.stdout or "").strip().startswith("{"):
                data = json.loads(r.stdout)
                for _, info in data.items():
                    if not isinstance(info, dict):
                        continue
                    total_b = info.get("VRAM Total Memory (B)") or info.get("VRAM Total Used Memory (B)")
                    used_b = info.get("VRAM Total Used Memory (B)")
                    if isinstance(total_b, (int, float)) and total_b > 0:
                        total_mb = _bytes_to_mb(total_b)
                        used_mb = _bytes_to_mb(used_b or 0)
                        gpus.append({"name": str(info.get("Card series") or info.get("Card SKU") or "AMD GPU"), "memory_total_mb": total_mb, "memory_free_mb": max(0, total_mb - used_mb)})
        except Exception:
            pass
        if not gpus:
            for cmd in [
                ["rocm-smi", "--showproductname", "--showmeminfo", "vram"],                 # 2
                ["rocm-smi", "--showproductname", "--showmeminfo", "all", "--json"],        # 3
                ["rocminfo"],                                                                # 4
                ["rocm_agent_enumerator"],                                                   # 5
            ]:
                try:
                    r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                    out = r.stdout or ""
                    if cmd[0] == "rocminfo":
                        for ln in out.splitlines():
                            if "Marketing Name" in ln:
                                gpus.append({"name": ln.split(":", 1)[-1].strip(), "memory_total_mb": -1, "memory_free_mb": -1})
                    elif cmd[0] == "rocm_agent_enumerator":
                        for ln in out.splitlines():
                            if ln.strip() and ln.strip() != "gfx000":
                                gpus.append({"name": f"AMD GPU {ln.strip()}", "memory_total_mb": -1, "memory_free_mb": -1})
                    else:
                        for ln in out.splitlines():
                            if "Card series" in ln or "Card SKU" in ln:
                                gpus.append({"name": ln.split(":", 1)[-1].strip(), "memory_total_mb": -1, "memory_free_mb": -1})
                    if gpus:
                        break
                except Exception:
                    continue
    elif backend == "nvidia-proc":
        # 5 strategies all from proc/sys sources
        try:
            base = "/proc/driver/nvidia/gpus"  # 1
            if os.path.isdir(base):
                for name in os.listdir(base):
                    info_path = os.path.join(base, name, "information")
                    if os.path.exists(info_path):
                        gpu_name = "NVIDIA GPU"
                        with open(info_path, "r", encoding="utf-8", errors="ignore") as f:
                            for line in f:
                                if line.lower().startswith("model:"):
                                    gpu_name = line.split(":", 1)[1].strip()
                        gpus.append({"name": gpu_name, "memory_total_mb": -1, "memory_free_mb": -1})
        except Exception:
            pass
        if not gpus and os.path.exists("/proc/driver/nvidia/version"):  # 2
            gpus.append({"name": "NVIDIA GPU (/proc version)", "memory_total_mb": -1, "memory_free_mb": -1})
        if not gpus:
            for path in ["/proc/modules", "/sys/module/nvidia/version", "/sys/class/drm"]:  # 3/4/5
                try:
                    if os.path.exists(path):
                        gpus.append({"name": "NVIDIA GPU (kernel module)", "memory_total_mb": -1, "memory_free_mb": -1})
                        break
                except Exception:
                    pass
    elif backend == "lspci":
        for cmd in [
            ["lspci"],                  # 1
            ["lspci", "-nn"],           # 2
            ["lspci", "-vnn"],          # 3
            ["lshw", "-C", "display"],  # 4
            ["hwinfo", "--gfxcard"],    # 5
        ]:
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
                for line in (r.stdout or "").splitlines():
                    low = line.lower()
                    if any(k in low for k in ["vga", "3d controller", "display", "model:"]) and any(v in low for v in ["nvidia", "amd", "advanced micro devices", "radeon", "geforce"]):
                        gpus.append({"name": line.split(":", 1)[-1].strip(), "memory_total_mb": -1, "memory_free_mb": -1})
                if gpus:
                    break
            except Exception:
                continue
    elif backend == "windows-counter" and os.name == "nt":
        # 最優先: レジストリから64bit正確なVRAM値を取得 (AdapterRAM uint32オーバーフロー回避)
        try:
            import winreg
            reg_base = r"SYSTEM\ControlSet001\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
            for ri in range(16):
                reg_sub = f"{reg_base}\\{ri:04d}"
                try:
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_sub) as rk:
                        try:
                            rname = str(winreg.QueryValueEx(rk, "DriverDesc")[0])
                        except OSError:
                            try:
                                rname = str(winreg.QueryValueEx(rk, "HardwareInformation.AdapterString")[0]).rstrip('\x00')
                            except OSError:
                                rname = ""
                        if not rname:
                            continue
                        vb = 0
                        for vkey in ("HardwareInformation.qwMemorySize", "HardwareInformation.MemorySize"):
                            try:
                                vb = int(winreg.QueryValueEx(rk, vkey)[0])
                                if vb > 0:
                                    break
                            except OSError:
                                continue
                        vmb = int(vb / (1024 * 1024)) if vb > 0 else -1
                        gpus.append({"name": rname, "memory_total_mb": vmb, "memory_free_mb": -1})
                except OSError:
                    continue
        except Exception:
            pass
        # フォールバック: WMI / CIM / PNP / wmic / dxdiag
        if not gpus:
            for ps in [
                "$gpu = Get-WmiObject Win32_VideoController | Where-Object { $_.AdapterRAM -gt 0 -and $_.Name -notmatch 'Virtual' } | Select-Object -First 1; "
                "$name = if ($gpu) { [string]$gpu.Name } else { 'Windows GPU' }; $totalB = if ($gpu) { [double]$gpu.AdapterRAM } else { 0 }; "
                "$obj = @{ name=$name; total_mb=[math]::Round($totalB/1MB) }; $obj | ConvertTo-Json -Compress",
                "Get-CimInstance Win32_VideoController | Select-Object -First 1 Name,AdapterRAM | ConvertTo-Json -Compress",
                "Get-PnpDevice -Class Display | Select-Object -ExpandProperty FriendlyName | ConvertTo-Json -Compress",
                "wmic path win32_VideoController get name,AdapterRAM",
                "dxdiag /whql:off /dontskip /t $env:TEMP\\dxdiag_gpu.txt; Get-Content $env:TEMP\\dxdiag_gpu.txt",
            ]:
                try:
                    r = subprocess.run(["powershell", "-Command", ps], capture_output=True, text=True, timeout=12)
                    out = (r.stdout or "").strip()
                    if not out:
                        continue
                    data = None
                    try:
                        data = json.loads(out)
                    except Exception:
                        data = None
                    if isinstance(data, dict):
                        name = str(data.get("Name") or data.get("name") or "Windows GPU")
                        total_mb = int((data.get("AdapterRAM") or data.get("total_mb") or 0) / (1024 * 1024)) if isinstance(data.get("AdapterRAM"), (int, float)) else int(data.get("total_mb") or -1)
                        gpus.append({"name": name, "memory_total_mb": total_mb, "memory_free_mb": -1})
                    elif isinstance(data, list):
                        for row in data:
                            gpus.append({"name": str(row if isinstance(row, str) else row.get("name") or row.get("Name") or "Windows GPU"), "memory_total_mb": -1, "memory_free_mb": -1})
                    else:
                        for line in out.splitlines():
                            if line.strip() and "name" not in line.lower():
                                gpus.append({"name": line.strip(), "memory_total_mb": -1, "memory_free_mb": -1})
                    if gpus:
                        break
                except Exception:
                    continue
    return gpus


def _select_working_gpu_backend(ports: UsageCollectorPorts, setting_key: str, candidates: list[str]) -> tuple[str, list[dict]]:
    preferred = (ports.settings.get_setting(setting_key) or "auto").strip()
    if preferred and preferred not in ("auto", "none"):
        g = _probe_gpu_static(preferred)
        if g:
            return preferred, g
    for b in candidates:
        g = _probe_gpu_static(b)
        if g:
            ports.settings.set_setting(setting_key, b)
            return b, g
    ports.settings.set_setting(setting_key, "none")
    return "none", []


def collect_system_usage_info(*, ports: UsageCollectorPorts, debug_mode: bool = False) -> dict[str, Any]:
    """
    現在のCPU/GPU使用率とRAM/VRAM使用量を返す。
    可能な限り依存なしで取得し、取得不可項目は -1 を返す。
    """
    cpu_percent = -1.0
    ram_total_mb = -1
    ram_used_mb = -1
    ram_percent = -1.0
    try:
        import psutil  # type: ignore
        cpu_percent = float(psutil.cpu_percent(interval=0.15))
        vm = psutil.virtual_memory()
        ram_total_mb = int(vm.total / (1024 * 1024))
        ram_used_mb = int((vm.total - vm.available) / (1024 * 1024))
        ram_percent = float(vm.percent)
    except Exception:
        try:
            if os.name == "nt":
                ps = (
                    "$os = Get-CimInstance Win32_OperatingSystem; "
                    "$cpu = (Get-Counter '\\Processor(_Total)\\% Processor Time').CounterSamples[0].CookedValue; "
                    "$total = [math]::Round($os.TotalVisibleMemorySize / 1024); "
                    "$avail = [math]::Round($os.FreePhysicalMemory / 1024); "
                    "$used = $total - $avail; "
                    "$ramPct = if ($total -gt 0) { ($used / $total) * 100 } else { 0 }; "
                    "Write-Output (\"{0},{1},{2},{3}\" -f [math]::Round($cpu,1),$total,$used,[math]::Round($ramPct,1))"
                )
                r = subprocess.run(["powershell", "-Command", ps], capture_output=True, text=True, timeout=8)
                out = (r.stdout or "").strip()
                if "," in out:
                    cpu_s, total_s, used_s, pct_s = out.split(",", 3)
                    cpu_percent = float(cpu_s)
                    ram_total_mb = int(total_s)
                    ram_used_mb = int(used_s)
                    ram_percent = float(pct_s)
            else:
                if hasattr(os, "getloadavg"):
                    load1, _, _ = os.getloadavg()
                    c = os.cpu_count() or 1
                    cpu_percent = max(0.0, min(100.0, (load1 / c) * 100.0))
                t_kb, a_kb = _read_meminfo_kb()
                if t_kb > 0:
                    ram_total_mb = _kb_to_mb(t_kb)
                if a_kb > 0 and ram_total_mb > 0:
                    ram_used_mb = max(0, ram_total_mb - _kb_to_mb(a_kb))
                    ram_percent = (ram_used_mb / ram_total_mb) * 100.0
        except Exception:
            pass

    def _windows_registry_gpu_vram() -> tuple[str, int]:
        """Windowsレジストリから GPU 名と VRAM(MB) を取得。64bit値対応で4GB超も正確。"""
        if os.name != "nt":
            return ("", -1)
        try:
            import winreg
            base_path = r"SYSTEM\ControlSet001\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
            best_name = ""
            best_vram_mb = -1
            for i in range(16):
                subkey = f"{base_path}\\{i:04d}"
                try:
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, subkey) as key:
                        try:
                            name = str(winreg.QueryValueEx(key, "DriverDesc")[0])
                        except OSError:
                            name = ""
                        # まず qwMemorySize (64bit QWORD) を試す
                        vram_bytes = 0
                        try:
                            vram_bytes = int(winreg.QueryValueEx(key, "HardwareInformation.qwMemorySize")[0])
                        except OSError:
                            pass
                        # フォールバック: MemorySize (DWORD, 4GB超でオーバーフローの可能性)
                        if vram_bytes <= 0:
                            try:
                                vram_bytes = int(winreg.QueryValueEx(key, "HardwareInformation.MemorySize")[0])
                            except OSError:
                                pass
                        if vram_bytes <= 0:
                            try:
                                val = winreg.QueryValueEx(key, "HardwareInformation.AdapterString")[0]
                                if val and not name:
                                    name = str(val).rstrip('\x00')
                            except OSError:
                                pass
                            continue
                        vram_mb = int(vram_bytes / (1024 * 1024))
                        if vram_mb > best_vram_mb:
                            best_name = name
                            best_vram_mb = vram_mb
                except OSError:
                    continue
            return (best_name, best_vram_mb)
        except Exception:
            return ("", -1)

    def _windows_dxdiag_dedicated_vram_mb() -> int:
        if os.name != "nt":
            return -1
        now = time.time()
        with _usage_diag_lock:
            cached_mb = int(_windows_dxdiag_cache.get("mb", -1))
            checked_at = float(_windows_dxdiag_cache.get("checked_at", 0.0))
        # 成功値は10分、失敗値は30秒キャッシュしてポーリング遅延を防ぐ
        if cached_mb > 0 and (now - checked_at) < 600:
            return cached_mb
        if cached_mb <= 0 and (now - checked_at) < 30:
            return -1
        tf_path = ""
        try:
            import tempfile
            with tempfile.NamedTemporaryFile(prefix="dxdiag_", suffix=".txt", delete=False) as tf:
                tf_path = tf.name
            subprocess.run(["dxdiag", "/64bit", "/whql:off", "/t", tf_path], capture_output=True, text=True, timeout=15)
            raw = b""
            with open(tf_path, "rb") as f:
                raw = f.read()
            txt = ""
            for enc in ("utf-16", "utf-8", "cp932"):
                try:
                    txt = raw.decode(enc)
                    if txt:
                        break
                except Exception:
                    continue
            if not txt:
                return -1
            m = re.search(r"Dedicated Memory:\s*([\d,]+)\s*(MB|GB)", txt, re.IGNORECASE)
            if not m:
                m = re.search(r"専用メモリ:\s*([\d,]+)\s*(MB|GB)", txt, re.IGNORECASE)
            if not m:
                return -1
            val = int(m.group(1).replace(",", ""))
            unit = (m.group(2) or "MB").upper()
            mb = int(val * 1024) if unit == "GB" else int(val)
            with _usage_diag_lock:
                _windows_dxdiag_cache["mb"] = mb
                _windows_dxdiag_cache["checked_at"] = now
            return mb
        except Exception:
            return -1
        finally:
            with _usage_diag_lock:
                # 失敗時もchecked_atだけ更新して連続実行を抑制
                if int(_windows_dxdiag_cache.get("mb", -1)) <= 0:
                    _windows_dxdiag_cache["checked_at"] = now
            try:
                if tf_path and os.path.exists(tf_path):
                    os.remove(tf_path)
            except Exception:
                pass

    def _windows_pdh_counter_values(path: str, sample_interval_s: float = 0.1) -> list[tuple[str, float]]:
        """Windows PDHをctypesで直接読み、ワイルドカードカウンタの全インスタンス
        (インスタンス名, 値) を返す。失敗時は空リスト。

        注意: PDHのステータスコード (PDH_MORE_DATA=0x800007D2 等) は符号なし32bitで
        比較する必要があるため、restype を c_uint32 に固定する。デフォルトの符号付き
        c_int のままだと 0x800007D2 が負数になり比較が常に失敗する。
        """
        if os.name != "nt":
            return []
        try:
            import ctypes
            from ctypes import wintypes

            PDH_MORE_DATA = 0x800007D2
            PDH_FMT_DOUBLE = 0x00000200
            PDH_CSTATUS_VALID_DATA = 0x00000000
            PDH_CSTATUS_NEW_DATA = 0x00000001

            class _PDH_FMT_COUNTERVALUE_UNION(ctypes.Union):
                _fields_ = [("longValue", ctypes.c_long), ("doubleValue", ctypes.c_double), ("largeValue", ctypes.c_longlong)]

            class _PDH_FMT_COUNTERVALUE(ctypes.Structure):
                _fields_ = [("CStatus", wintypes.DWORD), ("u", _PDH_FMT_COUNTERVALUE_UNION)]

            class _PDH_FMT_COUNTERVALUE_ITEM_W(ctypes.Structure):
                _fields_ = [("szName", ctypes.c_wchar_p), ("FmtValue", _PDH_FMT_COUNTERVALUE)]

            pdh = ctypes.WinDLL("pdh")
            for fn_name in ("PdhOpenQueryW", "PdhAddEnglishCounterW", "PdhAddCounterW",
                            "PdhCollectQueryData", "PdhGetFormattedCounterArrayW", "PdhCloseQuery"):
                fn = getattr(pdh, fn_name, None)
                if fn is not None:
                    fn.restype = ctypes.c_uint32

            hq = ctypes.c_void_p()
            if pdh.PdhOpenQueryW(None, 0, ctypes.byref(hq)) != 0 or not hq.value:
                return []
            try:
                # ワイルドカードパスを1つのカウンタとして登録し、配列APIで全インスタンスを
                # 一括取得する（インスタンスごとに個別クエリ+sleepすると数百インスタンスで
                # 数十秒かかるため）。
                hc = ctypes.c_void_p()
                add_english = getattr(pdh, "PdhAddEnglishCounterW", None)
                add_rc = add_english(hq, path, 0, ctypes.byref(hc)) if add_english else 1
                if add_rc != 0 or not hc.value:
                    # ローカライズ環境などでEnglishカウンタ登録に失敗した場合のフォールバック
                    add_rc = pdh.PdhAddCounterW(hq, path, 0, ctypes.byref(hc))
                if add_rc != 0 or not hc.value:
                    return []
                # 利用率カウンタは2サンプル必要
                if pdh.PdhCollectQueryData(hq) != 0:
                    return []
                time.sleep(sample_interval_s)
                pdh.PdhCollectQueryData(hq)

                size = wintypes.DWORD(0)
                count = wintypes.DWORD(0)
                rc = pdh.PdhGetFormattedCounterArrayW(hc, PDH_FMT_DOUBLE, ctypes.byref(size), ctypes.byref(count), None)
                if rc != PDH_MORE_DATA or size.value <= 0:
                    return []
                buf = (ctypes.c_byte * size.value)()
                rc = pdh.PdhGetFormattedCounterArrayW(
                    hc, PDH_FMT_DOUBLE, ctypes.byref(size), ctypes.byref(count),
                    ctypes.cast(buf, ctypes.POINTER(_PDH_FMT_COUNTERVALUE_ITEM_W)),
                )
                if rc != 0:
                    return []
                items = ctypes.cast(buf, ctypes.POINTER(_PDH_FMT_COUNTERVALUE_ITEM_W))
                out: list[tuple[str, float]] = []
                for i in range(count.value):
                    item = items[i]
                    if item.FmtValue.CStatus in (PDH_CSTATUS_VALID_DATA, PDH_CSTATUS_NEW_DATA):
                        out.append((str(item.szName or ""), float(item.FmtValue.u.doubleValue)))
                return out
            finally:
                pdh.PdhCloseQuery(hq)
        except Exception:
            return []

    def _windows_pdh_counter_max(path: str) -> float:
        """ワイルドカードカウンタの最大値（アダプタ単位の値向け）。失敗時-1。"""
        values = [v for _, v in _windows_pdh_counter_values(path, sample_interval_s=0.0)]
        return max(values) if values else -1.0

    def _windows_pdh_gpu_utilization() -> float:
        """タスクマネージャ準拠のGPU使用率: エンジン種別(engtype_*)ごとに全プロセスの
        利用率を合算し、その最大値を採用する。失敗時-1。"""
        values = _windows_pdh_counter_values(r"\GPU Engine(*)\Utilization Percentage", sample_interval_s=0.1)
        if not values:
            return -1.0
        by_engine: dict[str, float] = {}
        for name, v in values:
            m = re.search(r"engtype_([^_]+)$", name)
            key = m.group(1) if m else "unknown"
            by_engine[key] = by_engine.get(key, 0.0) + v
        best = max(by_engine.values()) if by_engine else -1.0
        return min(100.0, max(0.0, best)) if best >= 0 else -1.0

    candidates = ["nvidia-smi", "rocm-smi", "nvidia-proc", "lspci"] if os.name != "nt" else ["windows-counter", "nvidia-smi"]
    selected = (ports.settings.get_setting("gpu_usage_backend") or "auto").strip()
    if selected in ("", "auto", "none"):
        selected, _ = _select_working_gpu_backend(ports, "gpu_usage_backend", candidates)
    gpus = []
    parse_summary: list[dict] = []
    nvidia_fail_reason = ""
    parse_source = "unknown"
    gpu_backend = selected if selected else "none"
    cmd_timeout_sec = 8 if debug_mode else 2
    if selected == "nvidia-smi":
        nvidia_cmds = [
            ["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total", "--format=csv,noheader,nounits"],
            ["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total", "--format=csv,noheader"],
            ["nvidia-smi", "-q", "-d", "UTILIZATION,MEMORY"],
            ["nvidia-smi", "dmon", "-s", "u", "-c", "1"],
            ["nvidia-smi", "-L"],
        ]
        for cmd in (nvidia_cmds if debug_mode else nvidia_cmds[:2]):
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
                if r.returncode != 0 and not (r.stdout or "").strip():
                    parse_summary.append({
                        "cmd": " ".join(cmd),
                        "ok": False,
                        "reason": f"returncode={r.returncode}",
                        "stderr_head": (r.stderr or "").strip()[:120],
                    })
                    continue
                parsed_this_cmd = 0
                for line in (r.stdout or "").splitlines():
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) >= 4:
                        util = float(re.sub(r'[^0-9.]', '', parts[1]) or -1)
                        used = _parse_int_maybe(re.sub(r'[^0-9]', '', parts[2]))
                        total = _parse_int_maybe(re.sub(r'[^0-9]', '', parts[3]))
                        pct = _calculate_percent(used, total)
                        gpus.append({"name": parts[0], "util_percent": util, "vram_used_mb": used, "vram_total_mb": total, "vram_percent": pct})
                        parsed_this_cmd += 1
                parse_summary.append({
                    "cmd": " ".join(cmd),
                    "ok": parsed_this_cmd > 0,
                    "rows": parsed_this_cmd,
                })
                if gpus:
                    parse_source = "direct"
                    break
                nvidia_fail_reason = "parse fail"
            except FileNotFoundError:
                nvidia_fail_reason = "command not found"
                parse_summary.append({"cmd": " ".join(cmd), "ok": False, "reason": "command not found"})
                break
            except subprocess.TimeoutExpired:
                nvidia_fail_reason = "timeout"
                parse_summary.append({"cmd": " ".join(cmd), "ok": False, "reason": "timeout"})
                continue
            except Exception as e:
                nvidia_fail_reason = f"parse fail ({type(e).__name__})"
                parse_summary.append({"cmd": " ".join(cmd), "ok": False, "reason": f"parse fail: {type(e).__name__}"})
                continue
    elif selected == "rocm-smi":
        rocm_cmds = [
            ["rocm-smi", "--showuse", "--showmeminfo", "vram", "--json"],
            ["rocm-smi", "--showuse", "--showmemuse", "--json"],
            ["rocm-smi", "--showuse", "--showmemuse"],
            ["rocminfo"],
            ["rocm_agent_enumerator"],
        ]
        for cmd in (rocm_cmds if debug_mode else rocm_cmds[:2]):
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=cmd_timeout_sec)
                out = r.stdout or ""
                if "--json" in cmd:
                    data = json.loads(out or "{}")
                    for _, info in data.items() if isinstance(data, dict) else []:
                        if not isinstance(info, dict):
                            continue
                        util = float(str(info.get("GPU use (%)", "0")).replace("%", "") or -1)
                        vram_pct = float(str(info.get("GPU memory use (%)", "0")).replace("%", "") or -1)
                        vram_used_mb = -1
                        vram_total_mb = -1
                        # --showmeminfo vram provides VRAM Total/Used in bytes
                        total_b = info.get("VRAM Total Memory (B)")
                        used_b = info.get("VRAM Total Used Memory (B)")
                        if isinstance(total_b, (int, float)) and total_b > 0:
                            vram_total_mb = _bytes_to_mb(total_b)
                            if isinstance(used_b, (int, float)) and used_b >= 0:
                                vram_used_mb = _bytes_to_mb(used_b)
                                vram_pct = _calculate_percent(vram_used_mb, vram_total_mb)
                        # --showmemuse provides GPU memory use (%) only; try GTT as fallback for total
                        if vram_total_mb < 0:
                            for key_total in ("VRAM Total Memory (B)", "GTT Total Memory (B)"):
                                tb = info.get(key_total)
                                if isinstance(tb, (int, float)) and tb > 0:
                                    vram_total_mb = _bytes_to_mb(tb)
                                    break
                        if vram_used_mb < 0:
                            for key_used in ("VRAM Total Used Memory (B)", "GTT Total Used Memory (B)"):
                                ub = info.get(key_used)
                                if isinstance(ub, (int, float)) and ub >= 0:
                                    vram_used_mb = _bytes_to_mb(ub)
                                    break
                        if vram_pct < 0 and vram_used_mb >= 0 and vram_total_mb > 0:
                            vram_pct = _calculate_percent(vram_used_mb, vram_total_mb)
                        gpus.append({"name": str(info.get("Card series") or info.get("Card SKU") or "AMD GPU"), "util_percent": util, "vram_used_mb": vram_used_mb, "vram_total_mb": vram_total_mb, "vram_percent": vram_pct})
                else:
                    for line in out.splitlines():
                        if "Card series" in line or "Card SKU" in line:
                            gpus.append({"name": line.split(":",1)[-1].strip(), "util_percent": -1, "vram_used_mb": -1, "vram_total_mb": -1, "vram_percent": -1})
                if gpus:
                    parse_source = "direct"
                    break
            except Exception:
                continue
    elif selected == "windows-counter" and os.name == "nt":
        # まずはPython(ctypes + PDH)で直接カウンタを読む
        py_util = _windows_pdh_gpu_utilization()
        py_used_b = _windows_pdh_counter_max(r"\GPU Adapter Memory(*)\Dedicated Usage")
        py_ded_limit_b = _windows_pdh_counter_max(r"\GPU Adapter Memory(*)\Dedicated Limit")
        py_shr_limit_b = _windows_pdh_counter_max(r"\GPU Adapter Memory(*)\Shared Limit")
        py_total_b = max(py_ded_limit_b, py_shr_limit_b)
        # レジストリから GPU名 と VRAM総量(64bit正確値) を取得
        reg_name, reg_mb = _windows_registry_gpu_vram()
        # PDH Dedicated Limit が取れない場合のフォールバック順:
        # 1) レジストリ(64bit正確値) → 2) dxdiag
        if py_total_b <= 0:
            if reg_mb > 0:
                py_total_b = float(reg_mb * 1024 * 1024)
            else:
                dx_mb = _windows_dxdiag_dedicated_vram_mb()
                py_total_b = float(dx_mb * 1024 * 1024) if dx_mb > 0 else -1
        py_used_mb = int(round(py_used_b / (1024 * 1024))) if py_used_b >= 0 else -1
        py_total_mb = int(round(py_total_b / (1024 * 1024))) if py_total_b > 0 else -1
        py_pct = _calculate_percent(py_used_mb, py_total_mb)
        if py_util >= 0 or py_used_mb >= 0 or py_total_mb > 0:
            gpus.append({
                "name": reg_name or "Windows GPU",
                "util_percent": float(py_util),
                "vram_used_mb": py_used_mb,
                "vram_total_mb": py_total_mb,
                "vram_percent": py_pct,
            })
            parse_source = "direct"

        if gpus:
            pass
        else:
            windows_cmds = [
            "$adapters = Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue | "
            "  Where-Object { $_.AdapterRAM -gt 0 -and $_.Name -notmatch 'Virtual|Remote|Basic Display' }; "
            "$gpu = $adapters | Sort-Object AdapterRAM -Descending | Select-Object -First 1; "
            "$name = if ($gpu) { [string]$gpu.Name } else { 'Windows GPU' }; "
            "$totalB = if ($gpu) { [double]$gpu.AdapterRAM } else { -1 }; "
            "$engine = (Get-Counter '\\GPU Engine(*)\\Utilization Percentage' -ErrorAction SilentlyContinue).CounterSamples; "
            "$util = if ($engine) { [double](($engine | Measure-Object CookedValue -Maximum).Maximum) } else { -1 }; "
            "$dedicated = (Get-Counter '\\GPU Adapter Memory(*)\\Dedicated Usage' -ErrorAction SilentlyContinue).CounterSamples; "
            "$usedB = if ($dedicated) { [double](($dedicated | Measure-Object CookedValue -Maximum).Maximum) } else { -1 }; "
            "$dedicatedLimit = (Get-Counter '\\GPU Adapter Memory(*)\\Dedicated Limit' -ErrorAction SilentlyContinue).CounterSamples; "
            "$dedicatedLimitB = if ($dedicatedLimit) { [double](($dedicatedLimit | Measure-Object CookedValue -Maximum).Maximum) } else { -1 }; "
            "$sharedLimit = (Get-Counter '\\GPU Adapter Memory(*)\\Shared Limit' -ErrorAction SilentlyContinue).CounterSamples; "
            "$sharedLimitB = if ($sharedLimit) { [double](($sharedLimit | Measure-Object CookedValue -Maximum).Maximum) } else { -1 }; "
            "$counterTotalB = [Math]::Max($dedicatedLimitB, $sharedLimitB); "
            "if ($totalB -le 0 -and $counterTotalB -gt 0) { $totalB = $counterTotalB }; "
            "$totalMb = if ($totalB -gt 0) { [math]::Round($totalB / 1MB) } else { -1 }; "
            "$usedMb = if ($usedB -ge 0) { [math]::Round($usedB / 1MB) } else { -1 }; "
            "$vramPct = if ($totalMb -gt 0 -and $usedMb -ge 0) { [math]::Round(($usedMb / $totalMb) * 100, 1) } else { -1 }; "
            "$obj=@{ name=$name; util=[math]::Round($util,1); total_mb=$totalMb; used_mb=$usedMb; vram_pct=$vramPct }; "
            "$obj|ConvertTo-Json -Compress",
            "$gpu = Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue | "
            "  Where-Object { $_.AdapterRAM -gt 0 -and $_.Name -notmatch 'Virtual|Remote|Basic Display' } | "
            "  Sort-Object AdapterRAM -Descending | Select-Object -First 1; "
            "$name = if ($gpu) { [string]$gpu.Name } else { 'Windows GPU' }; "
            "$totalB = if ($gpu) { [double]$gpu.AdapterRAM } else { -1 }; "
            "$engine = (Get-Counter '\\GPU Engine(*)\\Utilization Percentage' -ErrorAction SilentlyContinue).CounterSamples; "
            "$util = if ($engine) { [double](($engine | Measure-Object CookedValue -Maximum).Maximum) } else { -1 }; "
            "$dedicated = (Get-Counter '\\GPU Adapter Memory(*)\\Dedicated Usage' -ErrorAction SilentlyContinue).CounterSamples; "
            "$usedB = if ($dedicated) { [double](($dedicated | Measure-Object CookedValue -Maximum).Maximum) } else { -1 }; "
            "$totalMb = if ($totalB -gt 0) { [math]::Round($totalB / 1MB) } else { -1 }; "
            "$usedMb = if ($usedB -ge 0) { [math]::Round($usedB / 1MB) } else { -1 }; "
            "$vramPct = if ($totalMb -gt 0 -and $usedMb -ge 0) { [math]::Round(($usedMb / $totalMb) * 100, 1) } else { -1 }; "
            "$obj=@{ name=$name; util=[math]::Round($util,1); total_mb=$totalMb; used_mb=$usedMb; vram_pct=$vramPct }; "
            "$obj|ConvertTo-Json -Compress",
            "Get-CimInstance Win32_VideoController | Select-Object -First 1 Name,AdapterRAM | ConvertTo-Json -Compress",
            "wmic path win32_VideoController get name,AdapterRAM",
            "Get-PnpDevice -Class Display | ConvertTo-Json -Compress",
        ]
            for ps in (windows_cmds if debug_mode else windows_cmds[:2]):
                try:
                    r = subprocess.run(["powershell", "-Command", ps], capture_output=True, text=True, timeout=(10 if debug_mode else 6))
                    out = (r.stdout or "").strip()
                    if not out:
                        continue
                    try:
                        data = json.loads(out)
                        if isinstance(data, dict):
                            total = int((data.get("AdapterRAM") or 0) / (1024*1024)) if isinstance(data.get("AdapterRAM"), (int,float)) else int(data.get("total_mb") or -1)
                            if total <= 0:
                                total = _windows_dxdiag_dedicated_vram_mb()
                            if total <= 0:
                                total = -1
                            used = int(data.get("used_mb") or -1)
                            pct = float(data.get("vram_pct") or -1)
                            if pct < 0 and used >= 0 and total > 0:
                                pct = _calculate_percent(used, total)
                            gpus.append({
                                "name": str(data.get("name") or data.get("Name") or "Windows GPU"),
                                "util_percent": float(data.get("util") or -1),
                                "vram_used_mb": used,
                                "vram_total_mb": total,
                                "vram_percent": pct,
                            })
                    except Exception:
                        for ln in out.splitlines():
                            if ln.strip() and "name" not in ln.lower():
                                gpus.append({"name": ln.strip(), "util_percent": -1, "vram_used_mb": -1, "vram_total_mb": -1, "vram_percent": -1})
                    if gpus:
                        parse_source = "direct"
                        break
                except Exception:
                    continue
    if not gpus:
        static_list = _probe_gpu_static(selected if selected != "none" else candidates[0])
        gpus = [_normalize_static_gpu_usage(g) for g in static_list]
        gpu_backend = selected
        if gpus:
            parse_source = "fallback"

    vram_confidence = "unknown"
    if str(parse_source).startswith("direct"):
        vram_confidence = "direct"
    elif parse_source == "fallback":
        vram_confidence = "fallback"

    adopted_values = {
        "gpu_count": len(gpus),
        "gpu0_name": gpus[0].get("name", "") if gpus else "",
        "gpu0_vram_used_mb": gpus[0].get("vram_used_mb", -1) if gpus else -1,
        "gpu0_vram_total_mb": gpus[0].get("vram_total_mb", -1) if gpus else -1,
        "gpu0_util_percent": gpus[0].get("util_percent", -1) if gpus else -1,
    }
    diag = {
        "gpu_backend_selected": selected,
        "gpu_backend": gpu_backend,
        "parse_source": parse_source,
        "nvidia_smi_failure_reason": nvidia_fail_reason if selected == "nvidia-smi" else "",
        "raw_parse_summary": parse_summary,
        "adopted_values": adopted_values,
        "updated_at": _usage_updated_at(),
    }
    ports.diagnostics.set_last_usage_diag(diag)

    return {
        "cpu_percent": round(cpu_percent, 1) if cpu_percent >= 0 else -1,
        "ram_total_mb": ram_total_mb,
        "ram_used_mb": ram_used_mb,
        "ram_percent": round(ram_percent, 1) if ram_percent >= 0 else -1,
        "gpu_backend": gpu_backend,
        "gpu_backend_selected": selected,
        "vram_source_backend": gpu_backend,
        "vram_confidence": vram_confidence,
        "gpus": gpus,
        "updated_at": _usage_updated_at(),
    }
