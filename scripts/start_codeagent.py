#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# Ensure project root is importable when this script is executed directly:
#   python scripts/start_codeagent.py
# This is required for Windows start.bat, where sys.path otherwise points to ./scripts.
_BASE_DIR_FOR_IMPORT = Path(__file__).resolve().parent.parent
if str(_BASE_DIR_FOR_IMPORT) not in sys.path:
    sys.path.insert(0, str(_BASE_DIR_FOR_IMPORT))

from app.env_detection import detect_gpu_profile, detect_os_profile, detect_runpod

AUTO_MODE_KEY = "auto"
AUTO_MODE_NUM = "1"
DEFAULT_SYS_VENV_NAME = "venv_sys"


def get_llama_root_dir(base_dir: Path, runpod: bool) -> Path:
    override = os.environ.get("LLAMA_ROOT_DIR", "").strip()
    if override:
        return Path(override)
    if runpod:
        return Path("/workspace/llama")
    return base_dir / "llama"


def detect_lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def copy_ui(base_dir: Path) -> None:
    src = base_dir / "ui.html"
    dst = base_dir / "ui" / "index.html"
    if not src.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    assets_src = base_dir / "assets"
    assets_dst = base_dir / "ui" / "assets"
    if assets_src.exists() and assets_src.is_dir():
        shutil.copytree(assets_src, assets_dst, dirs_exist_ok=True)
    logo_src = assets_src / "kasane-core-logo.svg"
    logo_dst = base_dir / "ui" / "kasane-core-logo.svg"
    if logo_src.exists():
        shutil.copy2(logo_src, logo_dst)
    print("[UI] ui.html copied (+ assets synced to /ui/assets)")


def resolve_llama_server_path(base_dir: Path, runpod: bool = False) -> Path:
    env_path = os.environ.get("LLAMA_SERVER_PATH", "").strip()
    if env_path:
        return Path(env_path)

    llama_root = get_llama_root_dir(base_dir, runpod=runpod)
    candidates = [
        llama_root / "llama-server",
        llama_root / "bin" / "llama-server",
        llama_root / "build" / "bin" / "llama-server",
        llama_root / "llama-server.exe",
    ]
    if runpod:
        candidates.extend(
            [
                Path("/workspace/llama-server"),
                Path("/workspace/llama/bin/llama-server"),
                Path("/workspace/llama/build/bin/llama-server"),
                Path("/workspace/llama.cpp/llama-server"),
                Path("/workspace/llama.cpp/bin/llama-server"),
                Path("/workspace/llama.cpp/build/bin/llama-server"),
                Path("/app/llama/llama-server"),
                Path("/app/llama/bin/llama-server"),
                Path("/app/llama/build/bin/llama-server"),
            ]
        )

    which_path = shutil.which("llama-server")
    if which_path:
        candidates.insert(0, Path(which_path))

    for path in candidates:
        if path.exists():
            return path
    return candidates[0] if platform.system().lower() != "windows" else candidates[-1]


def try_auto_setup_llama(base_dir: Path) -> bool:
    setup_script = base_dir / "scripts" / "setup_llama_runpod.sh"
    if not setup_script.exists():
        print(f"[Runpod][WARN] setup script not found: {setup_script}")
        return False
    cmd = ["bash", str(setup_script), "--install-if-needed"]
    print(f"[Runpod] Running llama auto-setup: {' '.join(cmd)}")
    try:
        completed = subprocess.run(cmd, cwd=base_dir, check=False)
    except Exception as e:
        print(f"[Runpod][WARN] llama auto-setup failed to start: {e}")
        return False
    if completed.returncode != 0:
        print(f"[Runpod][WARN] llama auto-setup failed with exit code {completed.returncode}")
        return False
    return True


def log_directory_tree(root: Path, max_depth: int = 3, max_entries: int = 200) -> None:
    if not root.exists():
        print(f"[Runpod] directory tree skipped (not found): {root}")
        return
    print(f"[Runpod] directory tree: {root}")
    shown = 0
    root = root.resolve()
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        depth = len(rel.parts)
        if depth > max_depth:
            continue
        indent = "  " * (depth - 1)
        suffix = "/" if path.is_dir() else ""
        print(f"[Runpod] {indent}- {rel}{suffix}")
        shown += 1
        if shown >= max_entries:
            print(f"[Runpod] ... truncated (>{max_entries} entries)")
            break


def ensure_llama_server(base_dir: Path, runpod: bool) -> Path | None:
    llama_path = resolve_llama_server_path(base_dir, runpod=runpod)
    if llama_path.exists():
        print(f"[LLM] llama-server found: {llama_path}")
        if runpod:
            log_directory_tree(get_llama_root_dir(base_dir, runpod=True), max_depth=3, max_entries=200)
        return llama_path

    if not runpod:
        print(f"[LLM][WARN] llama-server not found: {llama_path}")
        return None

    if os.environ.get("RUNPOD_AUTO_SETUP_LLAMA", "true").lower() == "false":
        print("[Runpod] RUNPOD_AUTO_SETUP_LLAMA=false -> skip llama setup.")
        return None

    print("[Runpod] llama-server not found. Trying auto setup...")
    if try_auto_setup_llama(base_dir):
        llama_path = resolve_llama_server_path(base_dir, runpod=runpod)
        if llama_path.exists():
            print(f"[Runpod] llama-server setup completed: {llama_path}")
            return llama_path
    print(
        "[Runpod][WARN] llama-server was not found after auto setup. "
        "Set LLAMA_SERVER_PATH directly or install llama.cpp (e.g. scripts/setup_llama_runpod.sh)."
    )


def request_json(url: str, timeout: float = 2.0) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as res:
            return json.loads(res.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        return None


def request_status(url: str, timeout: float = 2.0) -> int | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as res:
            return res.status
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        return None


def post_json(url: str, payload: dict, timeout: float = 5.0) -> int | None:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return res.status
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ConnectionError, OSError):
        return None


def wait_http_200(url: str, timeout_sec: int, label: str, proc: subprocess.Popen | None = None) -> bool:
    waited = 0
    while waited < timeout_sec:
        if proc is not None and proc.poll() is not None:
            print(f"[ERROR] {label} process exited early with code {proc.returncode}")
            return False
        status = request_status(url)
        if status == 200:
            print(f"[OK] {label} ready")
            return True
        time.sleep(2)
        waited += 2
        print(f"  {label} loading... {waited}s")
    return False


def choose_mode() -> tuple[str, str]:
    return AUTO_MODE_KEY, AUTO_MODE_NUM


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CodeAgent launcher (cross-platform)")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--primary-port", type=int, default=8080)
    parser.add_argument("--api-timeout", type=int, default=120)
    parser.add_argument("--llm-timeout", type=int, default=180)
    parser.add_argument("--no-kill-on-api-timeout", dest="no_kill_on_api_timeout", action="store_true")
    parser.add_argument("--kill-on-api-timeout", dest="no_kill_on_api_timeout", action="store_false")
    parser.set_defaults(no_kill_on_api_timeout=True)
    return parser.parse_args()


def _sys_venv_paths(base_dir: Path) -> tuple[Path, Path, Path]:
    _raw = os.environ.get("CODEAGENT_SYS_VENV_DIR", "").strip()
    venv_root = Path(_raw).expanduser() if _raw else base_dir / DEFAULT_SYS_VENV_NAME
    if os.name == "nt":
        py = venv_root / "Scripts" / "python.exe"
        pip = venv_root / "Scripts" / "pip.exe"
    else:
        py = venv_root / "bin" / "python"
        pip = venv_root / "bin" / "pip"
    return venv_root, py, pip


def _write_text_if_missing(path: Path, content: str) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"[Bootstrap] Created: {path}")


def _ensure_local_bootstrap_venv(base_dir: Path, env: dict[str, str]) -> tuple[str, bool]:
    """
    Local起動時:
      - 初回: venv_sys を作成して requirements を導入
      - 2回目以降: venv_sys があれば再利用
    """
    venv_root, venv_python, venv_pip = _sys_venv_paths(base_dir)
    created = False

    if not venv_python.exists():
        print(f"[Bootstrap] Creating system venv: {venv_root}")
        venv_root.mkdir(parents=True, exist_ok=True)
        mk = subprocess.run([sys.executable, "-m", "venv", str(venv_root)], cwd=base_dir, check=False)
        if mk.returncode != 0 or not venv_python.exists():
            print("[Bootstrap][WARN] Failed to create venv_sys. Fallback to current Python.")
            return sys.executable, False
        created = True
    else:
        print(f"[Bootstrap] Reusing system venv: {venv_root}")

    default_requirements = (
        "# Auto-generated on first local startup.\n"
        "# Add local bootstrap-only dependencies here if needed.\n"
        "fastapi\n"
        "uvicorn[standard]\n"
        "pydantic\n"
        "requests\n"
    )
    _write_text_if_missing(base_dir / "requirements.txt", default_requirements)

    # 初回のみ依存導入（2回目以降は既存環境を読み込む）
    if created and venv_pip.exists():
        req_txt = base_dir / "requirements.txt"
        if req_txt.exists():
            print("[Bootstrap] Installing Python dependencies into venv_sys...")
            install = subprocess.run([str(venv_pip), "install", "-r", str(req_txt)], cwd=base_dir, env=env, check=False)
            if install.returncode != 0:
                print("[Bootstrap][WARN] pip install failed. Continue with existing environment.")
    env["CODEAGENT_SYS_VENV_DIR"] = str(venv_root)
    env["CODEAGENT_SYS_VENV_PYTHON"] = str(venv_python)
    return str(venv_python), created


def main() -> int:
    args = parse_args()
    base_dir = Path(__file__).resolve().parent.parent
    runpod = detect_runpod()
    os_profile = detect_os_profile()
    gpu_profile = detect_gpu_profile()

    mode_key, mode_num = choose_mode()

    env = os.environ.copy()
    no_kill_on_api_timeout = args.no_kill_on_api_timeout
    env_toggle = env.get("CODEAGENT_NO_KILL_ON_API_TIMEOUT", "").strip().lower()
    if env_toggle in {"1", "true", "yes", "on"}:
        no_kill_on_api_timeout = True
    elif env_toggle in {"0", "false", "no", "off"}:
        no_kill_on_api_timeout = False
    env.setdefault("PYTHONUTF8", "1")
    env["CODEAGENT_LLM_PLANNER"] = f"http://127.0.0.1:{args.primary_port}/v1/chat/completions"
    env["CODEAGENT_LLM_EXECUTOR"] = f"http://127.0.0.1:{args.primary_port}/v1/chat/completions"
    env["CODEAGENT_LLM_CHAT"] = f"http://127.0.0.1:{args.primary_port}/v1/chat/completions"
    env["CODEAGENT_LLM_LIGHT"] = f"http://127.0.0.1:{args.primary_port}/v1/chat/completions"
    env["CODEAGENT_LLM_MODE"] = mode_num
    env.setdefault("DEFAULT_LLM_CTX_SIZE", "16384")
    env.setdefault("LLAMA_CTX_SIZE", env.get("DEFAULT_LLM_CTX_SIZE", "16384"))
    env.setdefault("NEXUS_ANSWER_LLM_MAX_CONTEXT_TOKENS", env.get("DEFAULT_LLM_CTX_SIZE", "16384"))
    if runpod:
        env.setdefault("CODEAGENT_CA_DATA_DIR", "/workspace/ca_data")
        env.setdefault("CODEAGENT_WORK_DIR", "/workspace/ca_data/workspace")
        env.setdefault("CODEAGENT_SKILLS_DIR", "/workspace/ca_data/skills")
        env.setdefault("CODEAGENT_STYLE_BERT_VITS2_MODELS_DIR", "/workspace/ca_data/tts/style_bert_vits2/models")
    env["CODEAGENT_LOCAL_GPU_VENDOR"] = str(gpu_profile.get("vendor") or "none")
    env["CODEAGENT_LOCAL_GPU_NAME"] = str(gpu_profile.get("name") or "")
    env["CODEAGENT_TTS_RECOMMENDED_DEVICE"] = str(gpu_profile.get("recommended_tts_device") or "cpu")
    env["CODEAGENT_LLAMA_RECOMMENDED_BACKEND"] = str(gpu_profile.get("recommended_llama_backend") or "cpu")
    if not env.get("CODEAGENT_STYLE_BERT_VITS2_DEVICE"):
        env["CODEAGENT_STYLE_BERT_VITS2_DEVICE"] = str(gpu_profile.get("recommended_tts_device") or "cpu")

    python_exec = sys.executable
    if not runpod:
        python_exec, _ = _ensure_local_bootstrap_venv(base_dir, env)

    print("==============================================")
    print(" CodeAgent Launcher")
    print(f" Mode    : {mode_key}")
    print(f" Runpod  : {'yes' if runpod else 'no'}")
    if runpod:
        print(f" CA_DATA : {env.get('CODEAGENT_CA_DATA_DIR', '/workspace/ca_data')}")
        print(f" WORKDIR : {env.get('CODEAGENT_WORK_DIR', '/workspace/ca_data/workspace')}")
        print(f" SKILLS  : {env.get('CODEAGENT_SKILLS_DIR', '/workspace/ca_data/skills')}")
        print(
            f" SBV2    : {env.get('CODEAGENT_STYLE_BERT_VITS2_MODELS_DIR', '/workspace/ca_data/tts/style_bert_vits2/models')}"
        )
    print("==============================================")
    print(f"[Env] OS: {os_profile.get('system') or 'unknown'}")
    print(f"[Env] Runpod: {'yes' if runpod else 'no'}")
    print(f"[Env] GPU: {gpu_profile.get('name') or 'none'}")
    print(f"[Env] GPU vendor: {gpu_profile.get('vendor') or 'none'}")
    print(f"[Env] TTS recommended device: {gpu_profile.get('recommended_tts_device') or 'cpu'}")
    backend_candidates = gpu_profile.get("backend_candidates") or []
    if backend_candidates:
        print(f"[Env] TTS backend candidates: {', '.join(str(x) for x in backend_candidates)}")
    print(f"[Env] llama backend recommendation: {gpu_profile.get('recommended_llama_backend') or 'cpu'}")

    copy_ui(base_dir)
    llama_path = ensure_llama_server(base_dir, runpod)
    if llama_path is not None:
        env["LLAMA_SERVER_PATH"] = str(llama_path)
        print(f"[LLM] LLAMA_SERVER_PATH={env['LLAMA_SERVER_PATH']}")
    else:
        env.pop("LLAMA_SERVER_PATH", None)
        print("[LLM][WARN] LLAMA_SERVER_PATH is unset because llama-server was not found.")

    uvicorn_cmd = [
        python_exec,
        "-m",
        "uvicorn",
        "main:app",
        "--host",
        args.host,
        "--port",
        str(args.port),
        "--log-level",
        "info",
        "--app-dir",
        str(base_dir),
    ]
    print(f"[FastAPI] Starting: {' '.join(uvicorn_cmd)}")
    proc = subprocess.Popen(uvicorn_cmd, cwd=base_dir, env=env)

    try:
        api_ok = wait_http_200(f"http://127.0.0.1:{args.port}/health", args.api_timeout, "FastAPI", proc=proc)
        if not api_ok:
            if proc.poll() is None and no_kill_on_api_timeout:
                print("[WARN] FastAPI health did not become ready before timeout, but process is still running.")
                print("[WARN] Keeping FastAPI process alive. Check logs or open the UI manually.")
                lan_ip = detect_lan_ip()
                print(f"[WARN] Local URL: http://localhost:{args.port}/")
                print(f"[WARN] LAN URL  : http://{lan_ip}:{args.port}/")
                return proc.wait()
            print("[ERROR] FastAPI did not become ready.")
            proc.terminate()
            return 1

        status = request_json(f"http://127.0.0.1:{args.port}/models/db/status")
        if not status:
            print("[ModelDB] status unavailable. Skipping LLM startup wait.")
            status = {}
        db_exists = bool(status.get("db_exists"))
        db_total = int(status.get("total", 0) or 0)
        benchmarked_total = int(status.get("benchmarked", 0) or 0)

        if db_exists and db_total > 0 and benchmarked_total > 0:
            print(
                f"[ModelDB] Found {db_total} model(s), benchmarked={benchmarked_total}. "
                "Requesting default LLM load..."
            )
            post_json(f"http://127.0.0.1:{args.port}/model/auto-load", {"reason": "launcher_py"})
            llm_ok = wait_http_200(f"http://127.0.0.1:{args.primary_port}/health", args.llm_timeout, "LLM")
            if not llm_ok:
                print(f"[WARN] LLM is still not ready after {args.llm_timeout}s.")
            else:
                # Warm-up: pre-fill KV cache so the first user request is fast
                print("[LLM] Sending warm-up request to pre-load KV cache...")
                warmup_payload = {
                    "messages": [{"role": "user", "content": "hi"}],
                    "max_tokens": 1,
                    "temperature": 0,
                }
                warmup_status = post_json(
                    f"http://127.0.0.1:{args.primary_port}/v1/chat/completions",
                    warmup_payload,
                    timeout=60.0,
                )
                if warmup_status and warmup_status < 300:
                    print("[LLM] Warm-up complete.")
                else:
                    print("[LLM][WARN] Warm-up request did not succeed (non-critical).")
        elif db_exists and db_total > 0:
            print(
                "[WAIT] model_db has models but no benchmarked models. "
                "Skipping LLM startup wait until UI benchmark completes."
            )
        elif db_exists and db_total <= 0:
            print("[WAIT] model_db is empty. FastAPI is ready; skipping LLM startup wait.")
        elif not db_exists:
            print("[WAIT] model_db is missing. FastAPI is ready; skipping LLM startup wait.")
        else:
            print("[WAIT] model_db status is unknown. FastAPI is ready; skipping LLM startup wait.")

        lan_ip = detect_lan_ip()
        print("\n==============================================")
        print(" CodeAgent ready!")
        print(f"  Local : http://localhost:{args.port}/")
        print(f"  LAN   : http://{lan_ip}:{args.port}/")
        print(f"  Mode  : {mode_num}  Profile: {mode_key}")
        print("==============================================")

        return proc.wait()
    except KeyboardInterrupt:
        print("\n[Launcher] Stopping...")
        proc.terminate()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
