#!/usr/bin/env python3
from __future__ import annotations

import argparse
import platform
import subprocess
import sys


def run(cmd: list[str]) -> tuple[int, str]:
    p = subprocess.run(cmd, capture_output=True, text=True)
    out = (p.stdout or "") + (p.stderr or "")
    return p.returncode, out.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Environment smoke check")
    parser.add_argument("--expect-python", default="3.11")
    args = parser.parse_args()

    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}"
    print(f"Python: {sys.version}")
    print(f"Platform: {platform.platform()}")

    if py_ver != args.expect_python:
        print(f"ERROR: Python {args.expect_python} is required, got {py_ver}")
        return 1

    code, msg = run(
        [sys.executable, "-c", "import fastapi,uvicorn,requests; print('imports-ok')"]
    )
    if code != 0:
        print("ERROR: dependency import failed")
        print(msg)
        return 1
    print(msg)

    for tool in ("nvidia-smi", "vulkaninfo"):
        code, _ = run([tool, "--help"])
        if code == 0:
            print(f"{tool}: available")
        else:
            print(f"{tool}: not available (non-blocking)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
