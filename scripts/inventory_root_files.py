#!/usr/bin/env python3
"""Inventory repository-root files for cleanup planning.

This script intentionally does not move files. It records root-level files,
heuristic cleanup ownership, and direct filename references from selected
project areas so docs/root_directory_inventory.md can be checked against a
machine-readable snapshot.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "docs" / "generated" / "root_directory_inventory.json"

ROOT_KEEP_EXACT = {
    ".dockerignore",
    ".gitignore",
    "Dockerfile",
    "LICENSE",
    "README.md",
    "docker-compose.yml",
    "compose.yml",
    "main.py",
    "pyproject.toml",
    "ui.html",
}
ROOT_KEEP_PREFIXES = ("requirements",)
SCRIPT_PREFIXES = ("check_", "collect_", "diagnose_", "export_", "verify_")
TOOL_PREFIXES = ("debug_", "migrate_", "repair_")
REFERENCE_ROOTS = [
    ".github/workflows",
    "scripts",
    "app",
    "docs",
    "tests",
]
REFERENCE_FILES = ["Dockerfile", "main.py", "README.md"]
EXCLUDED_REFERENCE_FILES = {
    "docs/generated/root_directory_inventory.json",
    "docs/root_directory_inventory.md",
    "tests/test_root_directory_inventory_contract.py",
}


@dataclass(frozen=True)
class RootFileRecord:
    name: str
    extension: str
    category: str
    move_candidate: bool
    suggested_owner: str
    suggested_destination: str
    reason: str
    references: list[str]
    caution: str


def _iter_text_files(paths: Iterable[Path]) -> Iterable[Path]:
    for path in paths:
        if path.is_file():
            yield path
        elif path.is_dir():
            yield from (child for child in path.rglob("*") if child.is_file())


def _reference_sources() -> list[Path]:
    roots = [ROOT / path for path in REFERENCE_ROOTS]
    files = [ROOT / path for path in REFERENCE_FILES]
    return sorted(set(_iter_text_files([*roots, *files])))


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return ""


def _find_references(filename: str, current_path: Path) -> list[str]:
    references: list[str] = []
    for source in _reference_sources():
        relative_source = source.relative_to(ROOT).as_posix()
        if (
            source.resolve() == current_path.resolve()
            or source.resolve() == Path(__file__).resolve()
            or relative_source in EXCLUDED_REFERENCE_FILES
        ):
            continue
        text = _read_text(source)
        if filename in text:
            references.append(relative_source)
    return references


def _classify(path: Path, references: list[str]) -> tuple[str, bool, str, str, str, str]:
    name = path.name
    suffix = path.suffix.lower()

    if name in ROOT_KEEP_EXACT or name.startswith(ROOT_KEEP_PREFIXES):
        return (
            "root-keep",
            False,
            "root",
            "root/",
            "Root entrypoint, build metadata, dependency manifest, or directly served UI asset.",
            "Do not move until Docker, launcher, README, and runtime references are updated together.",
        )
    if name == "agent_runtime.py":
        return (
            "needs-investigation",
            True,
            "tools",
            "tools/",
            "Root Python helper without a direct reference in the checked sources; ownership needs confirmation.",
            "Confirm manual launch expectations before moving.",
        )
    if name == "benchmark_mem.py":
        return (
            "tools-candidate",
            True,
            "tools",
            "tools/",
            "Manual/local memory benchmark utility, referenced by Runpod documentation/workflow guards.",
            "Move only after updating Runpod workflow/docs/test references.",
        )
    if name.startswith(SCRIPT_PREFIXES) and suffix == ".py":
        return (
            "scripts-candidate",
            True,
            "scripts",
            "scripts/",
            "One-shot or CI helper script prefix.",
            "Update any direct execution paths before moving.",
        )
    if name.startswith(TOOL_PREFIXES) and suffix == ".py":
        return (
            "tools-candidate",
            True,
            "tools",
            "tools/",
            "Manual debug/migration/repair utility prefix.",
            "Update manual runbooks before moving.",
        )
    if name.startswith("test_") and suffix == ".py":
        return (
            "tests-candidate",
            True,
            "tests",
            "tests/",
            "Test-like Python file at repository root.",
            "Check import assumptions before moving under tests/.",
        )
    if suffix in {".sh", ".ps1", ".bat"}:
        owner = "tools"
        destination = "tools/"
        category = "tools-candidate"
        if "setup" in name or "start" in name:
            category = "high-risk-launcher"
        return (
            category,
            True,
            owner,
            destination,
            "Root shell/Windows launcher or setup helper.",
            "High risk when referenced by users, Runpod, Windows setup docs, or runtime launch paths.",
        )
    if suffix == ".md":
        return (
            "docs-candidate",
            True,
            "docs",
            "docs/refactor/ or docs/runbooks/",
            "Root markdown that is not README.md.",
            "Preserve incoming links before moving.",
        )
    return (
        "needs-investigation",
        True,
        "undecided",
        "TBD",
        "No explicit cleanup rule matched.",
        "Investigate references and user-facing launch expectations before moving.",
    )


def build_inventory() -> dict[str, object]:
    root_files = sorted(path for path in ROOT.iterdir() if path.is_file() and path.name != ".git")
    records: list[RootFileRecord] = []
    for path in root_files:
        references = _find_references(path.name, path)
        category, move_candidate, owner, destination, reason, caution = _classify(path, references)
        records.append(
            RootFileRecord(
                name=path.name,
                extension=path.suffix or "<none>",
                category=category,
                move_candidate=move_candidate,
                suggested_owner=owner,
                suggested_destination=destination,
                reason=reason,
                references=references,
                caution=caution,
            )
        )

    return {
        "schema_version": 1,
        "generated_by": "scripts/inventory_root_files.py",
        "policy": "PR4.65 inventory only; no root-level files are moved by this script.",
        "reference_scan_scope": [*REFERENCE_FILES, *REFERENCE_ROOTS],
        "categories": sorted({record.category for record in records}),
        "files": [asdict(record) for record in records],
    }


def main() -> None:
    inventory = build_inventory()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT_PATH.relative_to(ROOT).as_posix()} ({len(inventory['files'])} root files)")


if __name__ == "__main__":
    main()
