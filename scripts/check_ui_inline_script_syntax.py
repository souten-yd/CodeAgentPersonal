#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UI_HTML = ROOT / "ui.html"
SCRIPT_RE = re.compile(r"<script(?P<attrs>[^>]*)>(?P<body>[\s\S]*?)</script>", re.IGNORECASE)


def main() -> int:
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
        ["node", "--check", str(tmp_path)],
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
