#!/usr/bin/env python3
"""
CodeAgent Memory Benchmark v2
VRAM: Get-Counter (Windows PDH) + llama-server log parsing
RAM:  Win32_OperatingSystem (PowerShell)
"""
import subprocess, requests, time, json, os, re
from datetime import datetime
from pathlib import Path

LLAMA_SERVER = r"C:\llama-cpp\llama-server.exe"
PORT         = 18099
BASE_URL     = f"http://127.0.0.1:{PORT}"
RESULT_DIR   = Path(r"C:\AI\benchmark")
RESULT_DIR.mkdir(exist_ok=True)

MODELS = {
    "lfm":     {"name":"LFM2.5-1.2B Q8_0",            "gpu":999, "path":r"E:\LLMs\models\lmstudio-community\LFM2.5-1.2B-Instruct-GGUF\LFM2.5-1.2B-Instruct-Q8_0.gguf"},
    "qwen9b":  {"name":"Qwen3.5-9B Q4_K_S",            "gpu":999, "path":r"E:\LLMs\unsloth\Qwen3.5-9B-GGUF\Qwen3.5-9B-Q4_K_S.gguf"},
    "gpt_oss": {"name":"GPT-OSS-20B Q4_K_M",            "gpu":999, "path":r"E:\LLMs\models\lmstudio-community\gpt-oss-20b-GGUF\gpt-oss-20b-Q4_K_M.gguf"},
    "gemma":   {"name":"Gemma-3-12B Q4_K_M",            "gpu":999, "path":r"E:\LLMs\models\lmstudio-community\gemma-3-12b-it-GGUF\gemma-3-12b-it-Q4_K_M.gguf"},
    "mistral": {"name":"Mistral-Small-3.2-24B Q3_K_S",  "gpu":999, "path":r"E:\LLMs\unsloth\Mistral-Small-3.2-24B-Instruct-2506-GGUF\Mistral-Small-3.2-24B-Instruct-2506-Q3_K_S.gguf"},
    "qwen35":  {"name":"Qwen3.5-35B-A3B Q4_K_M",        "gpu":999, "path":r"E:\LLMs\lmstudio-community\Qwen3.5-35B-A3B-GGUF\Qwen3.5-35B-A3B-Q4_K_M.gguf"},
    "coder":   {"name":"Qwen3-Coder-Next Q3_K_S",       "gpu":42,  "path":r"E:\LLMs\unsloth\Qwen3-Coder-Next-GGUF\Qwen3-Coder-Next-Q3_K_S.gguf"},
}

CTX_SIZES = [4096, 8192, 16384, 32768]

# ── VRAM (Get-Counter) ────────────────────────────────────────
def get_vram_mib() -> int:
    """Windows PDH カウンターで全GPU合計VRAM使用量を返す(MiB)"""
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
    except: pass
    return -1

# ── RAM (Win32_OperatingSystem) ───────────────────────────────
def get_ram_mib() -> int:
    """システムRAM使用量(MiB)"""
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
    except: pass
    return -1

def get_memory():
    return {"vram": get_vram_mib(), "ram": get_ram_mib()}

def measure_baseline():
    """3回平均でベースラインを取得"""
    samples = [get_memory() for _ in (time.sleep(1) or range(3))]
    vv = [s["vram"] for s in samples if s["vram"] >= 0]
    rv = [s["ram"]  for s in samples if s["ram"]  >= 0]
    return {
        "vram": round(sum(vv)/len(vv)) if vv else -1,
        "ram":  round(sum(rv)/len(rv)) if rv else -1,
    }

# ── llama-server log parser ───────────────────────────────────
def parse_llama_log(log_text: str) -> dict:
    """
    llama-serverのstderrからバッファサイズを抽出する。
    ROCm0 model buffer / KV buffer / RS buffer / compute buffer の合計を計算。
    CPU_Mapped は RAM 使用量として分類。
    """
    gpu_mib = 0
    cpu_mib = 0
    breakdown = {}

    patterns = [
        (r"ROCm0 model buffer size\s*=\s*([\d.]+)\s*MiB",   "gpu", "model_gpu"),
        (r"CPU_Mapped model buffer size\s*=\s*([\d.]+)\s*MiB","cpu", "model_cpu"),
        (r"ROCm0 KV buffer size\s*=\s*([\d.]+)\s*MiB",       "gpu", "kv_cache_gpu"),
        (r"ROCm0 RS buffer size\s*=\s*([\d.]+)\s*MiB",       "gpu", "rs_buffer"),
        (r"ROCm0 compute buffer size\s*=\s*([\d.]+)\s*MiB",  "gpu", "compute_gpu"),
        (r"ROCm_Host\s+output buffer size\s*=\s*([\d.]+)\s*MiB", "cpu", "output_host"),
        (r"ROCm_Host compute buffer size\s*=\s*([\d.]+)\s*MiB",  "cpu", "compute_host"),
    ]

    for pattern, kind, label in patterns:
        m = re.search(pattern, log_text)
        if m:
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

# ── プロセス管理 ──────────────────────────────────────────────
def kill_port(port):
    try:
        subprocess.run(
            ["powershell", "-Command",
             f"Get-NetTCPConnection -LocalPort {port} -EA SilentlyContinue | "
             f"Select -ExpandProperty OwningProcess | "
             f"% {{ Stop-Process -Id $_ -Force -EA SilentlyContinue }}"],
            capture_output=True, timeout=10)
    except: pass
    time.sleep(2)

def start_server_with_log(path, ctx, ngl=999):
    """
    起動してログを収集しながらヘルスチェック。
    (proc, load_sec, log_text) を返す。
    """
    kill_port(PORT)
    t0 = time.perf_counter()
    cmd = [LLAMA_SERVER, "--model", path, "--port", str(PORT),
           "--host", "127.0.0.1", "--ctx-size", str(ctx),
           "-ngl", str(ngl), "--threads", "8", "--no-mmap", "--no-warmup", "-np", "1"]

    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
    )

    log_lines = []
    ls = None

    # 非同期読み込みスレッド
    import threading
    def reader():
        for line in proc.stdout:
            log_lines.append(line)

    t = threading.Thread(target=reader, daemon=True)
    t.start()

    for _ in range(90):
        time.sleep(2)
        if proc.poll() is not None:
            break
        try:
            if requests.get(f"{BASE_URL}/health", timeout=2).status_code == 200:
                ls = time.perf_counter() - t0
                break
        except: pass

    time.sleep(1)  # ログバッファを少し待つ
    log_text = "".join(log_lines)
    return proc, ls, log_text

def stop_server(proc):
    if proc and proc.poll() is None:
        proc.terminate()
        try: proc.wait(timeout=8)
        except: proc.kill()
    kill_port(PORT)
    time.sleep(3)

# ── 推論速度 ──────────────────────────────────────────────────
def infer():
    payload = {
        "messages": [
            {"role": "system", "content": "You are a helpful assistant. " * 60},
            {"role": "user",   "content": "Write hello world in Python."},
        ],
        "max_tokens": 128, "temperature": 0.0,
    }
    try:
        t0 = time.perf_counter()
        data = requests.post(f"{BASE_URL}/v1/chat/completions",
                             json=payload, timeout=180).json()
        total = time.perf_counter() - t0
        u = data.get("usage", {}); tm = data.get("timings", {})
        pt = u.get("prompt_tokens", 0); ct = u.get("completion_tokens", 0)
        if tm:
            return {"ok": True, "prefill": round(tm.get("prompt_per_second", 0), 1),
                    "gen": round(tm.get("predicted_per_second", 0), 1),
                    "pt": pt, "ct": ct, "sec": round(total, 2)}
        elif pt > 0 and ct > 0 and total > 0:
            gs = total * ct / (pt + ct); ps = total - gs
            return {"ok": True,
                    "prefill": round(pt/ps, 1) if ps > 0 else 0,
                    "gen": round(ct/gs, 1) if gs > 0 else 0,
                    "pt": pt, "ct": ct, "sec": round(total, 2)}
        return {"ok": True, "prefill": 0, "gen": 0, "pt": pt, "ct": ct, "sec": round(total, 2)}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ── メイン ────────────────────────────────────────────────────
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
print("\n" + "=" * 65)
print(f"  CodeAgent Memory+Speed Benchmark v2  {ts}")
print("=" * 65)

print("\n[Baseline] Measuring OS memory (no LLM)...")
baseline = measure_baseline()
print(f"  VRAM: {baseline['vram']} MiB  RAM: {baseline['ram']} MiB")

results = {"baseline": baseline, "models": {}}

for key, info in MODELS.items():
    name = info["name"]; path = info["path"]; ngl = info["gpu"]
    print(f"\n{'='*50}\n[{name}]")
    if not os.path.exists(path):
        print("  SKIP: file not found")
        results["models"][key] = {"name": name, "skip": True}
        continue

    r = {"name": name, "ctx_results": {}}

    for ctx in CTX_SIZES:
        print(f"  ctx={ctx:6} loading...", end=" ", flush=True)
        proc, ls, log_text = start_server_with_log(path, ctx, ngl)

        if not ls or ls < 0:
            print("FAIL")
            stop_server(proc)
            r["ctx_results"][ctx] = {"ok": False}
            if ctx == CTX_SIZES[0]:
                break
            continue

        # ① llama-serverログからGPU/CPUバッファを解析
        log_mem = parse_llama_log(log_text)

        # ② Get-Counterで実VRAM使用量（ベースライン差分）
        time.sleep(1)
        mem_now = get_memory()
        vram_counter_delta = (mem_now["vram"] - baseline["vram"]
                              if mem_now["vram"] >= 0 and baseline["vram"] >= 0 else -1)
        ram_delta = (mem_now["ram"] - baseline["ram"]
                     if mem_now["ram"] >= 0 and baseline["ram"] >= 0 else -1)

        # ③ 推論速度（最初のctxのみ）
        inf_result = infer() if ctx == CTX_SIZES[0] else None

        cr = {
            "ok": True,
            "load_sec": round(ls, 1),
            # llama-server ログベース（正確）
            "log_gpu_mib": log_mem["gpu_total_mib"],
            "log_cpu_mib": log_mem["cpu_total_mib"],
            "log_total_mib": log_mem["gpu_total_mib"] + log_mem["cpu_total_mib"],
            "log_breakdown": log_mem["breakdown"],
            # Get-Counterベース（OS差分）
            "counter_vram_delta": vram_counter_delta,
            "counter_ram_delta": ram_delta,
            "inference": inf_result,
        }
        r["ctx_results"][ctx] = cr

        gen_str = ""
        if inf_result and inf_result.get("ok"):
            gen_str = f"  gen={inf_result['gen']} tok/s"

        print(
            f"OK  {ls:.1f}s | "
            f"LOG: GPU+{log_mem['gpu_total_mib']}MiB CPU+{log_mem['cpu_total_mib']}MiB | "
            f"CTR: VRAM+{vram_counter_delta}MiB RAM+{ram_delta}MiB"
            f"{gen_str}"
        )

        stop_server(proc)
        time.sleep(3)

    results["models"][key] = r

# ── 保存 ──────────────────────────────────────────────────────
json_path = RESULT_DIR / f"bench_mem_{ts}.json"
with open(json_path, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

# ── HTMLレポート ──────────────────────────────────────────────
def nb(v): return f"{v:,}" if isinstance(v, int) and v >= 0 else ("—" if v == -1 else str(v))

rows = []
for key, r in results["models"].items():
    if r.get("skip"):
        rows.append(f'<tr><td>{r["name"]}</td><td colspan="9" style="color:#f66">SKIP</td></tr>')
        continue
    first = next((r["ctx_results"][c] for c in CTX_SIZES
                  if r["ctx_results"].get(c, {}).get("ok")), {})
    inf = first.get("inference") or {}
    gen = inf.get("gen", "—") if inf.get("ok") else "FAIL"
    pre = inf.get("prefill", "—") if inf.get("ok") else "—"

    ctx_tds = ""
    for c in CTX_SIZES:
        cr = r["ctx_results"].get(c, {})
        if not cr.get("ok"):
            ctx_tds += '<td style="color:#555">—</td>'
        else:
            lg = cr.get("log_gpu_mib", -1)
            lc = cr.get("log_cpu_mib", -1)
            lt = cr.get("log_total_mib", -1)
            cv = cr.get("counter_vram_delta", -1)
            rm = cr.get("counter_ram_delta", -1)
            ctx_tds += (
                f'<td style="font-size:10px;line-height:1.6">'
                f'GPU {nb(lg)} MiB<br>'
                f'CPU {nb(lc)} MiB<br>'
                f'<b style="color:#0cf">LOG {nb(lt)} MiB</b><br>'
                f'<span style="color:#888">CTR VRAM+{nb(cv)}</span><br>'
                f'<span style="color:#888">CTR RAM+{nb(rm)}</span>'
                f'</td>'
            )

    rows.append(
        f'<tr>'
        f'<td style="white-space:nowrap">{r["name"]}</td>'
        f'<td style="color:#0f0;font-weight:bold">{gen}</td>'
        f'<td>{pre}</td>'
        f'<td>{first.get("load_sec", "—")}s</td>'
        + ctx_tds + '</tr>'
    )

html = (
    '<!DOCTYPE html><html><head><meta charset="utf-8">'
    f'<title>Mem Benchmark {ts}</title>'
    '<style>'
    'body{background:#0a0a0b;color:#e8e8f0;font-family:monospace;padding:20px}'
    'h1{color:#00ff88}'
    'table{border-collapse:collapse;width:100%;margin-top:12px}'
    'th{background:#1a1a2e;padding:7px 9px;border:1px solid #333;color:#0cf;font-size:11px}'
    'td{padding:5px 8px;border:1px solid #222;vertical-align:top}'
    'tr:nth-child(even){background:#0f0f18}'
    '</style></head><body>'
    '<h1>Memory + Speed Benchmark v2</h1>'
    f'<p style="color:#888">{ts}</p>'
    f'<p style="color:#888;font-size:11px">'
    f'Baseline VRAM(counter):{baseline["vram"]} MiB  RAM:{baseline["ram"]} MiB<br>'
    f'LOG = llama-server buffer sum (GPU+CPU)<br>'
    f'CTR = Get-Counter/Win32 delta from baseline (OS-subtracted)</p>'
    '<table><tr>'
    '<th>Model</th><th>Gen tok/s</th><th>Prefill tok/s</th><th>Load</th>'
    + "".join(f'<th>ctx={c}</th>' for c in CTX_SIZES)
    + '</tr>'
    + "".join(rows)
    + '</table>'
    '<pre style="margin-top:20px;background:#111;padding:14px;font-size:10px;overflow-x:auto">'
    + json.dumps(results, ensure_ascii=False, indent=2)
    + '</pre></body></html>'
)

html_path = RESULT_DIR / f"bench_mem_{ts}.html"
with open(html_path, "w", encoding="utf-8") as f:
    f.write(html)

# ── サマリー ──────────────────────────────────────────────────
print("\n" + "=" * 65)
print(f"SUMMARY (ctx={CTX_SIZES[0]})")
print(f"  Baseline VRAM:{baseline['vram']} MiB  RAM:{baseline['ram']} MiB")
print("=" * 65)
print(f"{'Model':<33} {'Gen':>7} {'LOG GPU':>9} {'LOG CPU':>9} {'LOG Tot':>9} {'CTR VRAM':>9} {'CTR RAM':>9}")
print("-" * 90)
for key, r in results["models"].items():
    if r.get("skip"):
        print(f"  {r['name']:<31} SKIP")
        continue
    c0 = r["ctx_results"].get(CTX_SIZES[0], {})
    if not c0.get("ok"):
        print(f"  {r['name']:<31} FAIL")
        continue
    inf = c0.get("inference") or {}
    g   = inf.get("gen", "—") if inf.get("ok") else "—"
    lg  = c0.get("log_gpu_mib", -1)
    lc  = c0.get("log_cpu_mib", -1)
    lt  = c0.get("log_total_mib", -1)
    cv  = c0.get("counter_vram_delta", -1)
    rm  = c0.get("counter_ram_delta", -1)
    print(f"  {r['name']:<31} {str(g):>7} {nb(lg):>9} {nb(lc):>9} {nb(lt):>9} {nb(cv):>9} {nb(rm):>9}")

print(f"\nHTML: {html_path}")
