#!/usr/bin/env python3
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UI_HTML = ROOT / "ui.html"
SCRIPT_RE = re.compile(r"<script(?P<attrs>[^>]*)>(?P<body>[\s\S]*?)</script>", re.IGNORECASE)


def resolve_node_binary() -> str:
  return os.environ.get("NODE_BINARY", "node")


def node_version_major(version_text: str) -> int | None:
  match = re.match(r"^v?(\d+)\.", version_text.strip())
  if not match:
    return None
  return int(match.group(1))


def validate_node_runtime(node_bin: str) -> tuple[bool, str, str]:
  node_path = shutil.which(node_bin) or node_bin
  try:
    result = subprocess.run(
      [node_bin, "--version"],
      capture_output=True,
      text=True,
      check=False,
    )
  except FileNotFoundError:
    print("Node.js >=18 is required for inline UI syntax checks.")
    print(f"Current node: {node_path}")
    print("Current version: unavailable (node binary not found)")
    return False, node_path, ""

  version_text = (result.stdout.strip() or result.stderr.strip() or "unknown")
  major = node_version_major(version_text)
  if result.returncode != 0 or major is None or major < 18:
    print("Node.js >=18 is required for inline UI syntax checks.")
    print(f"Current node: {node_path}")
    print(f"Current version: {version_text}")
    return False, node_path, version_text

  return True, node_path, version_text


def main() -> int:
  node_bin = resolve_node_binary()
  ok, node_path, node_version = validate_node_runtime(node_bin)
  if not ok:
    return 2

  print(f"Using node runtime: {node_path} ({node_version})")

  html = UI_HTML.read_text(encoding="utf-8")
  inline_scripts: list[str] = []
  for match in SCRIPT_RE.finditer(html):
    attrs = match.group("attrs") or ""
    if re.search(r"\bsrc\s*=", attrs, re.IGNORECASE):
      continue
    body = (match.group("body") or "").strip()
    if body:
      inline_scripts.append(body)

  if not inline_scripts:
    print("No inline script blocks found in ui.html")
    return 1

  for idx, script_body in enumerate(inline_scripts, start=1):
    with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8", delete=False) as tmp:
      tmp.write(script_body)
      tmp_path = Path(tmp.name)
    try:
      result = subprocess.run(
        [node_bin, "--check", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
      )
    finally:
      tmp_path.unlink(missing_ok=True)

    if result.returncode != 0:
      if result.stdout.strip():
        print(result.stdout.rstrip())
      if result.stderr.strip():
        print(result.stderr.rstrip())
      print(f"Inline script #{idx} has syntax errors")
      return result.returncode

  print(f"OK: {len(inline_scripts)} inline script block(s) passed node --check")
  return 0


if __name__ == "__main__":
  sys.exit(main())
