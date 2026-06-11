"""PIR-14 legacy dependency lint.

The lint freezes the currently known direct legacy consumers as an explicit allowlist and
fails when a new production module imports one of those legacy Project Intelligence
capabilities. It is a migration guard only; it does not cut over consumers or delete legacy
paths.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent.project_intelligence.inspection.consumer_inventory import build_inventory


def _consumer_key(legacy_module: str, consumer_path: str) -> str:
    return f"{legacy_module}|{consumer_path}"


def build_allowlist(root: str | Path, *, generated_at: str = "") -> dict[str, Any]:
    """Build an allowlist from the current source-derived consumer inventory."""
    inventory = build_inventory(Path(root))
    entries: list[dict[str, str]] = []
    for legacy in inventory.get("legacy_consumers", []):
        legacy_module = str(legacy.get("legacy_module") or "")
        capability = str(legacy.get("capability") or "")
        for consumer in legacy.get("production_consumers") or []:
            path = str(consumer.get("path") or "")
            if not legacy_module or not path:
                continue
            entries.append(
                {
                    "legacy_module": legacy_module,
                    "capability": capability,
                    "consumer_path": path,
                }
            )
    entries = sorted(entries, key=lambda row: (row["legacy_module"], row["consumer_path"]))
    return {
        "schema_version": 1,
        "source": "python_ast_current_checkout_legacy_dependency_allowlist",
        "generated_at": generated_at,
        "repository_root": Path(root).resolve().name,
        "entries": entries,
        "summary": {
            "allowed_dependency_count": len(entries),
            "legacy_module_count": len({entry["legacy_module"] for entry in entries}),
            "consumer_path_count": len({entry["consumer_path"] for entry in entries}),
        },
        "safety": {
            "allows_new_legacy_consumers": False,
            "consumer_cutover": False,
            "legacy_retirement": False,
        },
    }


def load_allowlist(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def lint_legacy_dependencies(root: str | Path, allowlist: dict[str, Any]) -> dict[str, Any]:
    """Return violations for current legacy imports missing from the allowlist."""
    inventory = build_inventory(Path(root))
    allowed = {
        _consumer_key(str(entry["legacy_module"]), str(entry["consumer_path"]))
        for entry in allowlist.get("entries", [])
    }
    violations: list[dict[str, str]] = []
    observed: list[dict[str, str]] = []
    for legacy in inventory.get("legacy_consumers", []):
        legacy_module = str(legacy.get("legacy_module") or "")
        capability = str(legacy.get("capability") or "")
        for consumer in legacy.get("production_consumers") or []:
            path = str(consumer.get("path") or "")
            if not legacy_module or not path:
                continue
            row = {
                "legacy_module": legacy_module,
                "capability": capability,
                "consumer_path": path,
            }
            observed.append(row)
            if _consumer_key(legacy_module, path) not in allowed:
                violations.append(row)

    observed = sorted(observed, key=lambda row: (row["legacy_module"], row["consumer_path"]))
    violations = sorted(violations, key=lambda row: (row["legacy_module"], row["consumer_path"]))
    return {
        "schema_version": 1,
        "source": "python_ast_current_checkout_legacy_dependency_lint",
        "repository_root": Path(root).resolve().name,
        "passed": not violations,
        "violations": violations,
        "summary": {
            "observed_dependency_count": len(observed),
            "allowed_dependency_count": len(allowed),
            "violation_count": len(violations),
        },
        "safety": {
            "consumer_cutover": False,
            "legacy_retirement": False,
        },
    }


def write_allowlist(root: str | Path, output: str | Path, *, generated_at: str = "") -> dict[str, Any]:
    allowlist = build_allowlist(root, generated_at=generated_at)
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(allowlist, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return allowlist


def write_lint_report(root: str | Path, allowlist: dict[str, Any], output: str | Path) -> dict[str, Any]:
    report = lint_legacy_dependencies(root, allowlist)
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report
