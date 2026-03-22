#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import platform
import subprocess
import sys


def run(cmd: list[str]) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True)
        out = (p.stdout or "") + (p.stderr or "")
        return p.returncode, out.strip()
    except FileNotFoundError as e:
        return 127, str(e)


def main() -> int:
    parser = argparse.ArgumentParser(description="Environment smoke check")
    parser.add_argument("--expect-python", default="")
    parser.add_argument("--strict", action="store_true",
                        help="return non-zero on python/dependency mismatch")
    args = parser.parse_args()

    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}"
    print(f"Python: {sys.version}")
    print(f"Platform: {platform.platform()}")

    if args.expect_python and py_ver != args.expect_python:
        msg = f"Python {args.expect_python} is required, got {py_ver}"
        if args.strict:
            print(f"ERROR: {msg}")
            return 1
        print(f"WARN: {msg}")

    required = ["fastapi", "uvicorn", "requests", "pydantic", "psutil"]
    missing = [m for m in required if importlib.util.find_spec(m) is None]
    if missing:
        print("WARN: dependency import failed")
        print(f"Missing modules: {', '.join(missing)}")
        print("Install command:")
        print("  python -m pip install -r requirements.txt")
        print("If you are behind a proxy/private mirror, set one of:")
        print("  PIP_INDEX_URL=https://<your-mirror>/simple")
        print("  python -m pip install -r requirements.txt --index-url https://<your-mirror>/simple")
        if args.strict:
            return 1
    print("imports-ok")


    optional = ["pynvml"]
    missing_optional = [m for m in optional if importlib.util.find_spec(m) is None]
    if missing_optional:
        print(f"WARN: optional modules missing for richer benchmark metrics: {', '.join(missing_optional)}")
        print("  python -m pip install nvidia-ml-py")
    else:
        print("optional-imports-ok")

    for tool in ("nvidia-smi", "vulkaninfo"):
        code, _ = run([tool, "--help"])
        if code == 0:
            print(f"{tool}: available")
        else:
            print(f"{tool}: not available (non-blocking)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
