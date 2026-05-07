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
WEB_JS_ROOT = ROOT / "web" / "js"
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


def iter_external_js_files() -> list[Path]:
  if not WEB_JS_ROOT.exists():
    return []
  return sorted(path for path in WEB_JS_ROOT.glob("**/*.js") if path.is_file())


def run_node_check(node_bin: str, path: Path) -> subprocess.CompletedProcess[str]:
  return subprocess.run(
    [node_bin, "--check", str(path)],
    capture_output=True,
    text=True,
    check=False,
  )


def print_node_check_output(result: subprocess.CompletedProcess[str]) -> None:
  if result.stdout.strip():
    print(result.stdout.rstrip())
  if result.stderr.strip():
    print(result.stderr.rstrip())


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

  external_js_files = iter_external_js_files()

  if not inline_scripts:
    print("No inline script blocks found in ui.html")
    if not external_js_files:
      return 1

  for idx, script_body in enumerate(inline_scripts, start=1):
    with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8", delete=False) as tmp:
      tmp.write(script_body)
      tmp_path = Path(tmp.name)
    try:
      result = run_node_check(node_bin, tmp_path)
    finally:
      tmp_path.unlink(missing_ok=True)

    if result.returncode != 0:
      print_node_check_output(result)
      print(f"Inline script #{idx} has syntax errors")
      return result.returncode

  for js_path in external_js_files:
    result = run_node_check(node_bin, js_path)
    if result.returncode != 0:
      print_node_check_output(result)
      print(f"External script {js_path.relative_to(ROOT)} has syntax errors")
      return result.returncode

  checked_targets: list[str] = []
  if inline_scripts:
    checked_targets.append(f"{len(inline_scripts)} inline script block(s)")
  if external_js_files:
    checked_targets.append(f"{len(external_js_files)} external script file(s)")
  print(f"OK: {' and '.join(checked_targets)} passed node --check")
  return 0


if __name__ == "__main__":
  sys.exit(main())
