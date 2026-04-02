#!/usr/bin/env python3
"""Health check for the LongCat-AudioDiT TTS venv.

Run this script with the LongCat venv Python to verify the environment:
    /workspace/.venvs/longcat-tts/bin/python scripts/check_longcat_tts.py

Or from the main CodeAgent environment (checks for the venv):
    python scripts/check_longcat_tts.py --from-main
"""

import argparse
import json
import os
import subprocess
import sys


def check_from_longcat_venv() -> dict:
    """Run inside the LongCat venv; verify all imports work."""
    repo_dir = os.environ.get("LONGCAT_REPO_DIR", "")
    if repo_dir and repo_dir not in sys.path:
        sys.path.insert(0, repo_dir)

    result = {"ok": True, "errors": [], "info": {}}

    pkgs = [
        ("torch", "torch"),
        ("torchaudio", "torchaudio"),
        ("transformers", "transformers"),
        ("soundfile", "soundfile"),
        ("librosa", "librosa"),
        ("numpy", "numpy"),
        ("einops", "einops"),
        ("safetensors", "safetensors"),
        ("huggingface_hub", "huggingface_hub"),
    ]
    for name, import_name in pkgs:
        try:
            mod = __import__(import_name)
            ver = getattr(mod, "__version__", "?")
            result["info"][name] = ver
        except ImportError as e:
            result["errors"].append(f"{name}: {e}")
            result["ok"] = False

    # audiodit (from repo)
    try:
        import audiodit  # noqa: F401
        result["info"]["audiodit"] = "ok"
    except ImportError as e:
        result["errors"].append(f"audiodit: {e}. LONGCAT_REPO_DIR={repo_dir}")
        result["ok"] = False

    # utils (from repo)
    try:
        from utils import normalize_text, approx_duration_from_text  # noqa: F401
        result["info"]["utils"] = "ok"
    except ImportError as e:
        result["errors"].append(f"utils: {e}")
        result["ok"] = False

    # CUDA
    try:
        import torch
        result["info"]["cuda_available"] = torch.cuda.is_available()
        if torch.cuda.is_available():
            result["info"]["cuda_device"] = torch.cuda.get_device_name(0)
    except Exception:
        pass

    # transformers version check
    try:
        import transformers
        from packaging.version import Version
        tv = Version(transformers.__version__)
        if tv < Version("5.3.0"):
            result["errors"].append(
                f"transformers version too old: {transformers.__version__} < 5.3.0. "
                "Re-run scripts/setup_longcat_tts.sh."
            )
            result["ok"] = False
        else:
            result["info"]["transformers_version_ok"] = True
    except ImportError:
        pass  # packaging may not be installed

    return result


def check_from_main(venv_dir: str, repo_dir: str) -> dict:
    """Called from the main CodeAgent venv; subproc into LongCat venv to check."""
    python = os.path.join(venv_dir, "bin", "python")
    if not os.path.isfile(python):
        return {"ok": False, "errors": [f"LongCat venv Python not found: {python}. Run scripts/setup_longcat_tts.sh."]}

    env = os.environ.copy()
    env["LONGCAT_REPO_DIR"] = repo_dir
    result = subprocess.run(
        [python, __file__],
        capture_output=True, text=True, timeout=60, env=env,
    )
    if result.returncode != 0:
        return {
            "ok": False,
            "errors": [f"Subprocess exited {result.returncode}"],
            "stderr": result.stderr[-2000:] if result.stderr else "",
            "stdout": result.stdout[-2000:] if result.stdout else "",
        }
    try:
        return json.loads(result.stdout.strip().splitlines()[-1])
    except Exception as e:
        return {
            "ok": False,
            "errors": [f"Could not parse output: {e}"],
            "stdout": result.stdout[-2000:] if result.stdout else "",
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-main", action="store_true",
                        help="Run from the main CodeAgent venv (will subproc into LongCat venv)")
    parser.add_argument("--venv-dir", default=os.environ.get("LONGCAT_TTS_VENV", "/workspace/.venvs/longcat-tts"))
    parser.add_argument("--repo-dir", default=os.environ.get("LONGCAT_REPO_DIR", "/workspace/LongCat-AudioDiT"))
    args = parser.parse_args()

    if args.from_main:
        result = check_from_main(args.venv_dir, args.repo_dir)
    else:
        result = check_from_longcat_venv()

    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
