#!/usr/bin/env python3
"""
CodeAgent Memory Benchmark helpers.
Safe to import from the server process.
"""
import os
import re
import signal
import subprocess
import time
from pathlib import Path
from typing import Optional, TextIO

import requests

try:
    import psutil
except Exception:  # optional dependency
    psutil = None

try:
    import pynvml
except Exception:  # optional dependency
    pynvml = None

BASE_DIR = Path(__file__).resolve().parent
PORT = 18099
BASE_URL = f"http://127.0.0.1:{PORT}"
RESULT_DIR = Path(os.environ.get("CODEAGENT_BENCH_DIR", str(BASE_DIR / "ca_data" / "benchmark")))
RESULT_DIR.mkdir(parents=True, exist_ok=True)
CTX_SIZES = [4096, 8192, 16384, 32768]


def _get_llama_server_path() -> str:
    """main.py と同じロジックで llama-server のパスを解決する。"""
    env_path = os.environ.get("LLAMA_SERVER_PATH", "").strip()
    if env_path:
        return env_path
    candidates = [
        str(BASE_DIR / "llama" / "llama-server.exe"),   # Windows
        str(BASE_DIR / "llama" / "llama-server"),        # Linux prebuilt
        str(BASE_DIR / "llama" / "bin" / "llama-server") # Linux source build
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return candidates[0] if os.name == "nt" else candidates[1]


LLAMA_SERVER = _get_llama_server_path()


def _detect_gpu_vendor() -> str:
    """nvidia / amd / unknown を返す。"""
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            return "nvidia"
    except Exception:
        pass
    try:
        r = subprocess.run(["rocm-smi"], capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            return "amd"
    except Exception:
        pass
    return "unknown"


def get_vram_mib() -> int:
    if pynvml is not None:
        try:
            pynvml.nvmlInit()
            count = pynvml.nvmlDeviceGetCount()
            total = 0
            for i in range(count):
                handle = pynvml.nvmlDeviceGetHandleByIndex(i)
                mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
                total += int(mem.used / (1024 * 1024))
            pynvml.nvmlShutdown()
            if total > 0:
                return total
        except Exception:
            pass

    if os.name == "nt":
        try:
            ps = (
                r"$samples = (Get-Counter '\GPU Adapter Memory(*)\Dedicated Usage' "
                r"-ErrorAction SilentlyContinue).CounterSamples; "
                r"$total = ($samples | Measure-Object CookedValue -Sum).Sum; "
                r"[math]::Round($total / 1MB)"
            )
            r = subprocess.run(
                ["powershell", "-Command", ps],
                capture_output=True, text=True, timeout=10
            )
            v = r.stdout.strip()
            if v and v.lstrip("-").isdigit():
                return int(v)
        except Exception:
            pass

    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10
        )
        vals = []
        for line in r.stdout.splitlines():
            line = line.strip()
            if line.isdigit():
                vals.append(int(line))
        if vals:
            return sum(vals)
    except Exception:
        pass
    return -1


def get_ram_mib() -> int:
    if psutil is not None:
        try:
            vm = psutil.virtual_memory()
            return round((vm.total - vm.available) / (1024 * 1024))
        except Exception:
            pass

    if os.name == "nt":
        try:
            ps = (
                "$os = Get-CimInstance Win32_OperatingSystem; "
                "[math]::Round(($os.TotalVisibleMemorySize - $os.FreePhysicalMemory) / 1024)"
            )
            r = subprocess.run(
                ["powershell", "-Command", ps],
                capture_output=True, text=True, timeout=10
            )
            v = r.stdout.strip()
            if v and v.lstrip("-").isdigit():
                return int(v)
        except Exception:
            pass
    return -1


def get_memory() -> dict:
    return {"vram": get_vram_mib(), "ram": get_ram_mib()}


def measure_baseline() -> dict:
    samples = []
    for _ in range(3):
        samples.append(get_memory())
        time.sleep(1)
    vv = [s["vram"] for s in samples if s["vram"] >= 0]
    rv = [s["ram"] for s in samples if s["ram"] >= 0]
    return {
        "vram": round(sum(vv) / len(vv)) if vv else -1,
        "ram": round(sum(rv) / len(rv)) if rv else -1,
    }


def parse_llama_log(log_text: str) -> dict:
    gpu_mib = 0
    cpu_mib = 0
    breakdown = {}
    patterns = [
        (r"(?:ROCm|CUDA|Vulkan|Metal)\d*\s+model buffer size\s*=\s*([\d.]+)\s*MiB", "gpu", "model_gpu"),
        (r"CPU(?:_Mapped)?\s+model buffer size\s*=\s*([\d.]+)\s*MiB", "cpu", "model_cpu"),
        (r"CPU(?:_Mapped)?\s+buffer size\s*=\s*([\d.]+)\s*MiB", "cpu", "buffer_cpu"),
        (r"(?:ROCm|CUDA|Vulkan|Metal)\d*\s+KV buffer size\s*=\s*([\d.]+)\s*MiB", "gpu", "kv_cache_gpu"),
        (r"CPU(?:_Mapped)?\s+KV buffer size\s*=\s*([\d.]+)\s*MiB", "cpu", "kv_cache_cpu"),
        (r"(?:ROCm|CUDA|Vulkan|Metal)\d*\s+RS buffer size\s*=\s*([\d.]+)\s*MiB", "gpu", "rs_buffer"),
        (r"(?:ROCm|CUDA|Vulkan|Metal)\d*\s+compute buffer size\s*=\s*([\d.]+)\s*MiB", "gpu", "compute_gpu"),
        (r"CPU(?:_Mapped)?\s+compute buffer size\s*=\s*([\d.]+)\s*MiB", "cpu", "compute_cpu"),
        (r"(?:ROCm|CUDA|Vulkan|Metal)_Host\s+output buffer size\s*=\s*([\d.]+)\s*MiB", "cpu", "output_host"),
        (r"(?:ROCm|CUDA|Vulkan|Metal)_Host\s+compute buffer size\s*=\s*([\d.]+)\s*MiB", "cpu", "compute_host"),
    ]
    for pattern, kind, label in patterns:
        m = re.search(pattern, log_text)
        if not m:
            continue
        val = round(float(m.group(1)))
        breakdown[label] = val
        if kind == "gpu":
            gpu_mib += val
        else:
            cpu_mib += val
    return {
        "gpu_total_mib": gpu_mib,
        "cpu_total_mib": cpu_mib,
        "breakdown": breakdown,
    }


def _parse_ngl_from_log(log_text: str) -> int:
    """ログから実際に使われた n_gpu_layers の値をパースする。"""
    m = re.search(r"n_gpu_layers\s*=\s*(\d+)", log_text)
    return int(m.group(1)) if m else -1


def _is_oom_log(log_text: str) -> bool:
    """ログからOOMを検出する。"""
    blob = log_text.lower()
    keywords = ("out of memory", "cudamalloc failed", "failed to allocate",
                "ggml_cuda_device_malloc", "insufficient vram")
    return any(kw in blob for kw in keywords)


def kill_port(port: int):
    """指定ポートを使用しているプロセスを停止する（Linux/Windows両対応）。"""
    if os.name == "nt":
        try:
            subprocess.run(
                [
                    "powershell", "-Command",
                    f"Get-NetTCPConnection -LocalPort {port} -EA SilentlyContinue | "
                    f"Select -ExpandProperty OwningProcess | "
                    f"% {{ Stop-Process -Id $_ -Force -EA SilentlyContinue }}",
                ],
                capture_output=True,
                timeout=10,
            )
        except Exception:
            pass
    else:
        # Linux: lsof or fuser でポートを使うPIDを特定してkill
        try:
            r = subprocess.run(
                ["lsof", "-ti", f":{port}"],
                capture_output=True, text=True, timeout=5,
            )
            for pid_str in r.stdout.strip().split():
                if pid_str.isdigit():
                    try:
                        os.kill(int(pid_str), signal.SIGTERM)
                    except OSError:
                        pass
        except Exception:
            pass
        try:
            subprocess.run(
                ["fuser", "-k", f"{port}/tcp"],
                capture_output=True, timeout=5,
            )
        except Exception:
            pass
    time.sleep(2)


def stop_server(proc):
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except Exception:
            proc.kill()
    kill_port(PORT)
    time.sleep(3)


def _start_server_once(path: str, ctx: int, ngl: int | None = None,
                       mmproj_path: str = "") -> tuple:
    """
    llama-server を1回起動してヘルスチェックまで行う。
    ngl=None の場合は -ngl を省略し、auto-fit に委ねる。
    Returns: (proc, load_sec_or_None, log_text, is_oom)
    """
    kill_port(PORT)
    t0 = time.perf_counter()
    cmd = [
        LLAMA_SERVER, "--model", path, "--port", str(PORT),
        "--host", "127.0.0.1", "--ctx-size", str(ctx),
        "--threads", "8", "--no-mmap", "--no-warmup", "-np", "1",
    ]
    if ngl is not None:
        cmd += ["-ngl", str(ngl)]
    if mmproj_path:
        cmd += ["--mmproj", mmproj_path]
    # NVIDIA GPU なら flash-attn を有効化
    gpu_vendor = _detect_gpu_vendor()
    if gpu_vendor == "nvidia":
        cmd += ["--flash-attn", "on"]

    ck, cv = resolve_llama_cache_types()
    if ck != "f16":
        cmd += ["--cache-type-k", ck]
    if cv != "f16":
        cmd += ["--cache-type-v", cv]

    ngl_display = str(ngl) if ngl is not None else "auto(fit)"
    print(f"[Benchmark] starting: -ngl={ngl_display} cache_k={ck} cache_v={cv} cmd={' '.join(cmd)}")

    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    popen_kwargs = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
    }
    if creationflags:
        popen_kwargs["creationflags"] = creationflags

    proc = subprocess.Popen(cmd, **popen_kwargs)
    log_lines: list[str] = []

    import threading
    def reader():
        stdout_pipe: Optional[TextIO] = proc.stdout
        if stdout_pipe is None:
            return
        for line in stdout_pipe:
            log_lines.append(line)

    threading.Thread(target=reader, daemon=True).start()
    load_sec = None
    for _ in range(90):
        time.sleep(2)
        if proc.poll() is not None:
            break
        try:
            if requests.get(f"{BASE_URL}/health", timeout=2).status_code == 200:
                load_sec = time.perf_counter() - t0
                break
        except Exception:
            pass
    time.sleep(1)
    log_text = "".join(log_lines)
    is_oom = _is_oom_log(log_text) if load_sec is None else False
    return proc, load_sec, log_text, is_oom


def start_server_with_log(path: str, ctx: int, ngl: int = 999,
                          mmproj_path: str = "") -> tuple:
    """
    プラットフォーム別の起動フロー:
      Windows  : auto-fit のみ（-ngl 省略、llama.cppに任せる）
      Linux    : 明示的 -ngl + OOMリトライ（proven_ngl / 計算値ベース）
    Returns: (proc, load_sec, log_text)
    """
    if os.name == "nt":
        return _start_windows_autofit(path, ctx, mmproj_path)
    else:
        return _start_linux_explicit_ngl(path, ctx, ngl, mmproj_path)


def _start_windows_autofit(path: str, ctx: int, mmproj_path: str) -> tuple:
    """Windows: auto-fit に完全に委ねる（-ngl 省略）。"""
    print("[Benchmark] Windows: auto-fit で起動")
    proc, load_sec, log_text, _ = _start_server_once(
        path, ctx, ngl=None, mmproj_path=mmproj_path,
    )
    if load_sec is None and any(x in (log_text or "").lower() for x in ["unsupported cache type", "unknown argument", "requires flash attention", "kv cache", "cache-type"]):
        os.environ["LLAMA_CACHE_TYPE_K"] = "f16"
        os.environ["LLAMA_CACHE_TYPE_V"] = "f16"
        print("[Benchmark][WARN] KV cache args failed; retrying with f16/f16")
        proc, load_sec, log_text, _ = _start_server_once(path, ctx, ngl=None, mmproj_path=mmproj_path)
    if load_sec is not None:
        actual_ngl = _parse_ngl_from_log(log_text)
        print(f"[Benchmark] auto-fit 成功 (n_gpu_layers={actual_ngl})")
    return proc, load_sec, log_text


def _start_linux_explicit_ngl(path: str, ctx: int, ngl: int,
                              mmproj_path: str) -> tuple:
    """
    Linux (Runpod/CUDA):
      Phase 1: auto-fit（-ngl省略）
      Phase 2: 半減リトライで最初の成功値を発見
      Phase 3: 成功値と失敗値の間で二分探索して最適値を確定
    """
    # ─── Phase 1: auto-fit を試行 ───────────────────────────
    print("[Benchmark] Linux Phase 1: auto-fit で起動を試行")
    proc, load_sec, log_text, is_oom = _start_server_once(
        path, ctx, ngl=None, mmproj_path=mmproj_path,
    )
    if load_sec is not None:
        actual_ngl = _parse_ngl_from_log(log_text)
        print(f"[Benchmark] auto-fit 成功 (n_gpu_layers={actual_ngl})")
        return proc, load_sec, log_text
    stop_server(proc)
    if not is_oom:
        print("[Benchmark] auto-fit失敗(非OOM) → Phase 2へ")

    # ─── Phase 2: 半減リトライで最初の成功値を発見 ───────────
    gpu_layers = ngl
    fail_ngl = gpu_layers
    ok_ngl = -1

    _OOM_MAX_RETRIES = 4
    for attempt in range(_OOM_MAX_RETRIES + 1):
        print(f"[Benchmark] Linux Phase 2: -ngl={gpu_layers} ({attempt + 1}/{_OOM_MAX_RETRIES + 1})")
        proc, load_sec, log_text, is_oom = _start_server_once(
            path, ctx, ngl=gpu_layers, mmproj_path=mmproj_path,
        )
        if load_sec is not None:
            ok_ngl = gpu_layers
            break
        stop_server(proc)
        if not is_oom:
            print(f"[Benchmark] 非OOMエラーで失敗")
            return proc, None, log_text
        fail_ngl = min(fail_ngl, gpu_layers)
        if gpu_layers <= 0:
            print(f"[Benchmark] gpu_layers=0でもOOM")
            return proc, None, log_text
        prev = gpu_layers
        gpu_layers = max(0, gpu_layers // 2)
        print(f"[Benchmark] OOM検出 → gpu_layers {prev} → {gpu_layers}")

    if ok_ngl < 0:
        print("[Benchmark] Phase 2: OOMリトライ回数超過")
        return proc, None, log_text

    # ─── Phase 3: 二分探索で最適値を確定 ─────────────────────
    stop_server(proc)
    lo = ok_ngl
    hi = fail_ngl
    best = ok_ngl
    _BISECT_MAX = 3

    if hi - lo > 1:
        print(f"[Benchmark] Linux Phase 3: 二分探索 [{lo}..{hi}] で最適値を探索")

    for _bisect_attempt in range(_BISECT_MAX):
        if hi - lo <= 1:
            break
        mid = (lo + hi) // 2
        print(f"[Benchmark] Phase 3: 二分探索 -ngl={mid} (範囲 [{lo}..{hi}])")
        proc, load_sec, log_text, is_oom = _start_server_once(
            path, ctx, ngl=mid, mmproj_path=mmproj_path,
        )
        if load_sec is not None:
            best = mid
            lo = mid
            stop_server(proc)
        else:
            hi = mid
            stop_server(proc)

    # best で最終起動
    print(f"[Benchmark] Phase 3: 最適値 -ngl={best} で最終起動")
    proc, load_sec, log_text, _ = _start_server_once(
        path, ctx, ngl=best, mmproj_path=mmproj_path,
    )
    if load_sec is not None:
        print(f"[Benchmark] 最適値 -ngl={best} で起動成功")
    return proc, load_sec, log_text


def infer() -> dict:
    payload = {
        "messages": [
            {"role": "system", "content": "You are a helpful assistant. " * 60},
            {"role": "user", "content": "Write hello world in Python."},
        ],
        "max_tokens": 128,
        "temperature": 0.0,
    }
    try:
        t0 = time.perf_counter()
        data = requests.post(f"{BASE_URL}/v1/chat/completions", json=payload, timeout=180).json()
        total = time.perf_counter() - t0
        usage = data.get("usage", {})
        timings = data.get("timings", {})
        pt = usage.get("prompt_tokens", 0)
        ct = usage.get("completion_tokens", 0)
        if timings:
            return {
                "ok": True,
                "prefill": round(timings.get("prompt_per_second", 0), 1),
                "gen": round(timings.get("predicted_per_second", 0), 1),
                "pt": pt,
                "ct": ct,
                "sec": round(total, 2),
            }
        if pt > 0 and ct > 0 and total > 0:
            gen_sec = total * ct / (pt + ct)
            prefill_sec = total - gen_sec
            return {
                "ok": True,
                "prefill": round(pt / prefill_sec, 1) if prefill_sec > 0 else 0,
                "gen": round(ct / gen_sec, 1) if gen_sec > 0 else 0,
                "pt": pt,
                "ct": ct,
                "sec": round(total, 2),
            }
        return {"ok": True, "prefill": 0, "gen": 0, "pt": pt, "ct": ct, "sec": round(total, 2)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def run_single_benchmark(path: str, ctx: int = 4096, ngl: int = 999, mmproj_path: str = "") -> dict:
    baseline = measure_baseline()
    if not os.path.exists(LLAMA_SERVER):
        return {"ok": False, "error": f"llama-server not found: {LLAMA_SERVER}", "baseline": baseline}
    if not os.path.exists(path):
        return {"ok": False, "error": f"file not found: {path}", "baseline": baseline}
    if mmproj_path and not os.path.exists(mmproj_path):
        return {"ok": False, "error": f"mmproj file not found: {mmproj_path}", "baseline": baseline}
    try:
        proc, load_sec, log_text = start_server_with_log(path, ctx, ngl, mmproj_path=mmproj_path)
    except Exception as e:
        return {"ok": False, "error": f"failed to start benchmark server: {e}", "baseline": baseline}
    if not load_sec:
        stop_server(proc)
        return {"ok": False, "error": "server did not start", "baseline": baseline,
                "log_text": log_text[-4000:] if log_text else ""}
    time.sleep(1)
    log_mem = parse_llama_log(log_text)
    mem_now = get_memory()
    inf = infer()
    stop_server(proc)
    return {
        "ok": True,
        "baseline": baseline,
        "load_sec": round(load_sec, 1),
        "log_gpu_mib": log_mem["gpu_total_mib"],
        "log_cpu_mib": log_mem["cpu_total_mib"],
        "log_total_mib": log_mem["gpu_total_mib"] + log_mem["cpu_total_mib"],
        "log_breakdown": log_mem["breakdown"],
        "counter_vram_delta": (mem_now["vram"] - baseline["vram"]) if mem_now["vram"] >= 0 and baseline["vram"] >= 0 else -1,
        "counter_ram_delta": (mem_now["ram"] - baseline["ram"]) if mem_now["ram"] >= 0 and baseline["ram"] >= 0 else -1,
        "inference": inf,
    }


def main():
    print("benchmark_mem.py is a helper module. Import its functions or call run_single_benchmark().")


if __name__ == "__main__":
    main()
