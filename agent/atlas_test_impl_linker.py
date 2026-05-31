"""Link a failing TEST plan item back to the implementation item it covers.

When a separate test item (e.g. ``tests/test_foo.py``) fails, the failure may be caused by a bug in the
CODE it exercises, not the test. To route the fix to the right artifact, we must find the
implementation item that owns ``foo.py``. This resolver is deliberately conservative and read-only:
it returns ``{}`` when the link is ambiguous (more than one match) or absent, so the caller safely
falls back to regenerating the test itself.

Matching = test-name convention (``test_foo.py``/``foo_test.py`` -> stem ``foo``) plus stems of modules
the test imports, intersected with implementation items' ``target_files`` stems. Mirrors the test-name
logic in ``agent/atlas_verification_resolver._is_python_test``.
"""
from __future__ import annotations

import re
from pathlib import PurePosixPath

_CODE_SUFFIXES = (".py", ".js", ".ts", ".jsx", ".tsx")


def _is_python_test(rel: str) -> bool:
    name = PurePosixPath(rel).name
    return (name.startswith("test_") and name.endswith(".py")) or name.endswith("_test.py")


def _impl_stem_from_test(rel: str) -> str:
    name = PurePosixPath(rel).name
    if name.endswith("_test.py"):
        return name[: -len("_test.py")]
    if name.startswith("test_") and name.endswith(".py"):
        return name[len("test_") : -len(".py")]
    return ""


def _stems_from_imports(test_content: str) -> set[str]:
    """Best-effort: module stems imported by the test (``from pkg.foo import x`` / ``import foo``)."""
    stems: set[str] = set()
    for m in re.finditer(r"^\s*(?:from\s+([\w\.]+)\s+import|import\s+([\w\.]+))", test_content or "", re.M):
        mod = (m.group(1) or m.group(2) or "").strip()
        if mod:
            stems.add(mod.split(".")[-1])
    stems.discard("")
    return stems


def find_implementation_item(*, pool, test_item, test_content: str = "") -> dict:
    """Return ``{"item_id", "files"}`` of the implementation item the failing test covers, or ``{}``.

    Conservative: requires a single-file Python test item, and a unique matching implementation item.
    """
    files = [str(f).strip() for f in (getattr(test_item, "target_files", None) or []) if str(f).strip()]
    if len(files) != 1 or not _is_python_test(files[0]):
        return {}

    candidate_stems: set[str] = set()
    stem = _impl_stem_from_test(files[0])
    if stem:
        candidate_stems.add(stem)
    candidate_stems |= _stems_from_imports(test_content)
    if not candidate_stems:
        return {}

    match: dict | None = None
    for it in (getattr(pool, "items", None) or []):
        if getattr(it, "item_id", None) == getattr(test_item, "item_id", None):
            continue
        if str(getattr(it, "item_type", "")) != "implementation":
            continue
        it_files = [str(f).strip() for f in (getattr(it, "target_files", None) or []) if str(f).strip()]
        for f in it_files:
            if _is_python_test(f):
                continue
            p = PurePosixPath(f)
            if p.suffix not in _CODE_SUFFIXES:
                continue
            if p.stem in candidate_stems:
                if match is not None and match["item_id"] != it.item_id:
                    return {}  # ambiguous: more than one implementation item matches
                match = {"item_id": it.item_id, "files": it_files}
                break
    return match or {}
