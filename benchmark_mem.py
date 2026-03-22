#!/usr/bin/env python3
"""
CodeAgent Memory Benchmark helpers.
Safe to import from the server process.
"""
import os
import re
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
LLAMA_SERVER = os.environ.get("LLAMA_SERVER_PATH", str(BASE_DIR / "llama" / "llama-server.exe"))
PORT = 18099
BASE_URL = f"http://127.0.0.1:{PORT}"
RESULT_DIR = Path(os.environ.get("CODEAGENT_BENCH_DIR", str(BASE_DIR / "ca_data" / "benchmark")))
RESULT_DIR.mkdir(parents=True, exist_ok=True)
CTX_SIZES = [4096, 8192, 16384, 32768]


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
        (r"(?:ROCm|CUDA|Vulkan|Metal)\d*\s+KV buffer size\s*=\s*([\d.]+)\s*MiB", "gpu", "kv_cache_gpu"),
        (r"(?:ROCm|CUDA|Vulkan|Metal)\d*\s+RS buffer size\s*=\s*([\d.]+)\s*MiB", "gpu", "rs_buffer"),
        (r"(?:ROCm|CUDA|Vulkan|Metal)\d*\s+compute buffer size\s*=\s*([\d.]+)\s*MiB", "gpu", "compute_gpu"),
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


def kill_port(port: int):
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
    time.sleep(2)


def start_server_with_log(path: str, ctx: int, ngl: int = 999, mmproj_path: str = ""):
    kill_port(PORT)
    t0 = time.perf_counter()
    cmd = [
        LLAMA_SERVER, "--model", path, "--port", str(PORT),
        "--host", "127.0.0.1", "--ctx-size", str(ctx),
        "-ngl", str(ngl), "--threads", "8", "--no-mmap", "--no-warmup", "-np", "1",
    ]
    if mmproj_path:
        cmd.extend(["--mmproj", mmproj_path])
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    log_lines = []

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
    return proc, load_sec, "".join(log_lines)


def stop_server(proc):
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except Exception:
            proc.kill()
    kill_port(PORT)
    time.sleep(3)


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
    if not os.path.exists(path):
        return {"ok": False, "error": f"file not found: {path}", "baseline": baseline}
    if mmproj_path and not os.path.exists(mmproj_path):
        return {"ok": False, "error": f"mmproj file not found: {mmproj_path}", "baseline": baseline}
    proc, load_sec, log_text = start_server_with_log(path, ctx, ngl, mmproj_path=mmproj_path)
    if not load_sec:
        stop_server(proc)
        return {"ok": False, "error": "server did not start", "baseline": baseline}
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
