"""Project mode detection (PI-4).

Classifies a project directory into one of the contract modes (contracts doc §6.1):
empty, greenfield_partial, existing, generated_unverified, imported_unknown.

Per the contract, ``.git``, ``.gitignore``, ``.gitkeep``, OS metadata, Atlas metadata, and
empty documentation do not by themselves make a project ``existing``. Detection is pure
(filesystem read only) and deterministic.
"""

from __future__ import annotations

from pathlib import Path

from agent.project_intelligence.contracts import ProjectMode

# Names that never count as project source.
_IGNORE_NAMES = {
    ".git", ".gitignore", ".gitkeep", ".gitattributes", ".editorconfig",
    ".ds_store", "thumbs.db", "desktop.ini",
    ".atlas", "atlas_workspace", "ca_data", "work",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".venv", "venv", "node_modules",
    "license", "license.md", "license.txt",
}

# Documentation that is not, by itself, evidence of an existing project.
_DOC_SUFFIXES = {".md", ".rst", ".txt"}

# Source extensions that indicate real implementation.
_SOURCE_SUFFIXES = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".rb", ".c", ".cc",
    ".cpp", ".h", ".hpp", ".cs", ".php", ".kt", ".swift", ".sql", ".vue", ".svelte",
}

_GREENFIELD_PARTIAL_MAX = 3  # a handful of source files == partial scaffolding


def _looks_like_test(name: str, rel_parts: tuple[str, ...]) -> bool:
    if name.startswith("test_") or name.endswith("_test.py") or name.endswith(".test.js"):
        return True
    if name.endswith("_test.go") or name.endswith(".spec.ts") or name.endswith(".spec.js"):
        return True
    # A directory component named tests/test/__tests__ marks the file as a test.
    return any(part.lower() in {"tests", "test", "__tests__"} for part in rel_parts[:-1])


def _classify_files(project_path: Path) -> dict[str, int]:
    root = project_path.resolve()
    source = 0
    tests = 0
    nonempty_docs = 0
    other_significant = 0
    if not root.is_dir():
        return {"source": 0, "tests": 0, "docs": 0, "other": 0}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part.lower() in _IGNORE_NAMES for part in rel.parts):
            continue
        suffix = path.suffix.lower()
        name = path.name.lower()
        if suffix in _SOURCE_SUFFIXES:
            source += 1
            if _looks_like_test(name, rel.parts):
                tests += 1
        elif suffix in _DOC_SUFFIXES:
            try:
                if path.stat().st_size > 0 and path.read_text(encoding="utf-8", errors="ignore").strip():
                    nonempty_docs += 1
            except OSError:
                pass
        else:
            other_significant += 1
    return {"source": source, "tests": tests, "docs": nonempty_docs, "other": other_significant}


def detect_project_mode(project_path: str | Path) -> ProjectMode:
    """Classify the project into a contract ProjectMode (deterministic, read-only)."""
    counts = _classify_files(Path(project_path))
    source = counts["source"]
    tests = counts["tests"]

    if source == 0:
        # No source: empty (ignoring git/docs/metadata) regardless of docs.
        return ProjectMode.EMPTY
    if source <= _GREENFIELD_PARTIAL_MAX and tests == 0:
        # A little scaffolding, not yet a coherent project.
        return ProjectMode.GREENFIELD_PARTIAL
    if tests > 0:
        # Real source with tests: an existing project.
        return ProjectMode.EXISTING
    if source > _GREENFIELD_PARTIAL_MAX and tests == 0:
        # Substantial source but no tests/verification: looks generated, unverified.
        return ProjectMode.GENERATED_UNVERIFIED
    return ProjectMode.IMPORTED_UNKNOWN
