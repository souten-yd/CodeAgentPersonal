"""Pillar E: auto-resolve which allowlisted verification command runs for an item.

Test execution + the failure->fix self-correction loop already exist; the missing piece is connecting
a plan item to a concrete test command so verification actually runs. This resolver inspects the item's
target file (and, when possible, related tests in the project) and returns a verification spec the
existing AtlasAutoVerificationService understands: {command_id, test_file} (or test_path).

Deliberately conservative and allowlist-bound: only Python pytest targets and JS `node --check` for the
two known dashboard assets. Never raises; returns {} when nothing applies.
"""
from __future__ import annotations

from pathlib import PurePosixPath


def _is_python_test(rel: str) -> bool:
    name = PurePosixPath(rel).name
    return name.startswith("test_") and name.endswith(".py") or name.endswith("_test.py")


def resolve_verification_for_item(*, target_files: list[str], project_path: str = "") -> dict:
    """Return {command_id, test_file/test_path} for the item, or {} if no safe verification applies.

    Priority:
    1. The item itself writes a Python test file -> run it directly (pytest_file).
    2. The item writes a non-test Python file that has a sibling/related test in the project -> run
       that related test (best-effort, requires project_path).
    """
    files = [str(f).strip() for f in (target_files or []) if str(f).strip()]
    if len(files) != 1:
        return {}
    rel = files[0]
    p = PurePosixPath(rel)
    if p.is_absolute() or ".." in p.parts:
        return {}

    if _is_python_test(rel):
        return {"command_id": "pytest_file", "test_file": rel}

    if rel.endswith(".py") and project_path:
        try:
            from agent.atlas_code_explorer import find_related_tests

            related = find_related_tests(project_path, [rel], max_tests=1)
            if related:
                return {"command_id": "pytest_file", "test_file": related[0]}
        except Exception:  # noqa: BLE001
            return {}
    return {}
