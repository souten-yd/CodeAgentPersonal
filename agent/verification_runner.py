from __future__ import annotations

import ast
from pathlib import Path
from uuid import uuid4

from agent.verification_schema import VerificationCheck, VerificationResult


class VerificationRunner:
    def __init__(self, max_file_bytes: int = 200 * 1024) -> None:
        self.max_file_bytes = max_file_bytes

    def run(self, run_id: str, plan_id: str, patch_id: str, project_path: Path, target_file: Path, replacement_hint: str = "") -> VerificationResult:
        checks: list[VerificationCheck] = []
        warnings: list[str] = []
        errors: list[str] = []

        def add(name: str, ok: bool, message: str, details: str = ""):
            checks.append(VerificationCheck(check_id=f"check_{len(checks)+1}", name=name, status="passed" if ok else "failed", message=message, details=details))
            if not ok:
                errors.append(f"{name}: {message}")

        add("target exists", target_file.exists(), "file exists" if target_file.exists() else "missing")
        if target_file.exists():
            raw = target_file.read_bytes()
            add("no null bytes", b"\x00" not in raw, "null bytes checked")
            try:
                text = raw.decode("utf-8")
                add("utf-8 readable", True, "utf-8 decode ok")
            except Exception as exc:
                text = ""
                add("utf-8 readable", False, f"decode error: {exc}")
            add("size limit", target_file.stat().st_size <= self.max_file_bytes, "size checked")
            add("inside project", project_path.resolve() in target_file.resolve().parents or project_path.resolve() == target_file.resolve(), "path checked")
            add("ca_data untouched", "ca_data" not in target_file.resolve().parts, "path policy checked")
            marker_ok = ("CodeAgent Phase 7 patch note" in text) or (replacement_hint and replacement_hint[:80] in text)
            add("marker/replacement exists", bool(marker_ok), "marker or replacement checked")
            add("no destructive marker", "DELETE" not in text and "run_command" not in text, "destructive markers checked")
            if target_file.suffix == ".py":
                try:
                    ast.parse(text)
                    add("python ast.parse", True, "syntax parse ok")
                except Exception as exc:
                    add("python ast.parse", False, f"syntax parse failed: {exc}")
        status = "passed" if not errors else "failed"
        summary = "verification passed" if status == "passed" else "verification failed"
        return VerificationResult(
            verification_id=f"ver_{uuid4().hex[:12]}",
            run_id=run_id,
            plan_id=plan_id,
            patch_id=patch_id,
            status=status,
            checks=checks,
            summary=summary,
            warnings=warnings,
            errors=errors,
        )
