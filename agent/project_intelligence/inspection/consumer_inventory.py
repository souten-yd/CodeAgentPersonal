"""Source-derived Project Intelligence consumer inventory.

The PIR-0 recovery baseline is intentionally read-only: it inventories the current
production imports, construction sites, facade/adapters, disabled/concrete modules,
and durable-store defaults without changing runtime behavior.
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


LEGACY_CAPABILITY_MODULES: dict[str, str] = {
    "agent.atlas_repo_index_service": "legacy_repository_index",
    "agent.atlas_code_intel_service": "legacy_code_intelligence",
    "agent.atlas_code_explorer": "legacy_code_explorer",
    "agent.atlas_project_inspection_service": "legacy_project_inspection",
    "agent.atlas_git_inspection_service": "legacy_git_inspection",
    "agent.atlas_repo_context_service": "legacy_repo_context",
    "agent.atlas_repo_context_planner_packager": "legacy_planner_context",
    "agent.atlas_plan_item_impact_map_service": "legacy_impact_map",
    "agent.atlas_verification_recommendation_service": "legacy_verification_recommendation",
    "agent.atlas_verification_recommendation_handoff_service": "legacy_verification_recommendation",
    "agent.atlas_verification_gate_service": "legacy_verification_gate",
    "agent.atlas_context_refresh_service": "legacy_context_refresh",
    "agent.atlas_context_refresh_v2_service": "legacy_context_refresh",
}

FACADE_MODULES: dict[str, str] = {
    "agent.project_intelligence.facade": "ProjectIntelligenceModule",
    "agent.project_intelligence.coordinator": "ProjectIntelligenceCoordinator",
    "agent.project_twin.facade": "DigitalTwinModule",
    "agent.architecture_blueprint.facade": "ArchitectureBlueprintModule",
    "agent.architecture_blueprint.module": "ArchitectureBlueprintModuleImpl",
    "agent.project_convergence.facade": "ConvergenceModule",
}

ADAPTER_MODULES: dict[str, str] = {
    "agent.project_intelligence.adapters.atlas_inspection": "inspection",
    "agent.project_intelligence.adapters.atlas_context_refresh": "context_refresh_api",
    "agent.project_intelligence.adapters.atlas_repo_context": "repo_context_api",
    "agent.project_intelligence.adapters.planner_packaging_v2": "planner_packaging_v2",
    "agent.project_intelligence.adapters.atlas_planning": "planning",
    "agent.project_intelligence.adapters.atlas_generation": "generation",
    "agent.project_intelligence.adapters.atlas_verification": "verification",
}

PRODUCTION_ROOTS = ("agent", "app")
PYTHON_SUFFIX = ".py"
DEFAULT_EXCLUDES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    "__pycache__",
    "node_modules",
    "venv",
    ".venv",
    "venv_sys",
    "tts_envs",
}
SQLITE_MEMORY_LITERAL = ":" + "memory" + ":"


@dataclass
class ParsedModule:
    module: str
    path: Path
    imports: list[str] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)
    string_literals: list[str] = field(default_factory=list)
    parse_error: str | None = None


class _Visitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.imports: list[str] = []
        self.calls: list[str] = []
        self.classes: list[str] = []
        self.string_literals: list[str] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.append(alias.name)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            self.imports.append(node.module)
            for alias in node.names:
                self.imports.append(f"{node.module}.{alias.name}")

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.classes.append(node.name)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        name = _call_name(node.func)
        if name:
            self.calls.append(name)
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str):
            self.string_literals.append(node.value)


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


def _module_name(root: Path, path: Path) -> str:
    return ".".join(path.relative_to(root).with_suffix("").parts)


def _iter_python_files(root: Path) -> list[Path]:
    paths: list[Path] = []
    for base in PRODUCTION_ROOTS:
        start = root / base
        if not start.exists():
            continue
        for path in start.rglob(f"*{PYTHON_SUFFIX}"):
            if any(part in DEFAULT_EXCLUDES for part in path.relative_to(root).parts):
                continue
            paths.append(path)
    return sorted(paths)


def _parse_module(root: Path, path: Path) -> ParsedModule:
    parsed = ParsedModule(module=_module_name(root, path), path=path)
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError) as exc:
        parsed.parse_error = str(exc)
        return parsed
    visitor = _Visitor()
    visitor.visit(tree)
    parsed.imports = sorted(set(visitor.imports))
    parsed.calls = sorted(set(visitor.calls))
    parsed.classes = sorted(set(visitor.classes))
    parsed.string_literals = sorted(set(visitor.string_literals))
    return parsed


def _rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _matches_import(imports: list[str], module: str) -> bool:
    return any(imp == module or imp.startswith(f"{module}.") for imp in imports)


def _call_matches(call: str, symbol: str) -> bool:
    return call == symbol or call.endswith(f".{symbol}")


def _construction_sites(root: Path, modules: list[ParsedModule], class_names: set[str]) -> list[dict[str, str]]:
    sites: list[dict[str, str]] = []
    for parsed in modules:
        for call in parsed.calls:
            for class_name in class_names:
                if _call_matches(call, class_name):
                    sites.append(
                        {
                            "module": parsed.module,
                            "path": _rel(root, parsed.path),
                            "class_name": class_name,
                            "call": call,
                        }
                    )
    return sorted(sites, key=lambda row: (row["path"], row["class_name"], row["call"]))


def _production_entrypoints(root: Path, modules: list[ParsedModule]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for parsed in modules:
        rel = _rel(root, parsed.path)
        if not rel.startswith("app/api/"):
            continue
        if "atlas" not in rel and "project_twin" not in rel:
            continue
        rows.append(
            {
                "module": parsed.module,
                "path": rel,
                "imports_project_intelligence": any(
                    imp.startswith("agent.project_intelligence") for imp in parsed.imports
                ),
                "imports_legacy_capability": sorted(
                    capability
                    for module, capability in LEGACY_CAPABILITY_MODULES.items()
                    if _matches_import(parsed.imports, module)
                ),
            }
        )
    return sorted(rows, key=lambda row: row["path"])


def _legacy_consumers(root: Path, modules: list[ParsedModule]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    adapter_modules = set(ADAPTER_MODULES)
    legacy_owner_modules = set(LEGACY_CAPABILITY_MODULES)
    for legacy_module, capability in LEGACY_CAPABILITY_MODULES.items():
        consumers = []
        adapter_consumers = []
        legacy_internal_consumers = []
        for parsed in modules:
            if not _matches_import(parsed.imports, legacy_module):
                continue
            row = {
                "module": parsed.module,
                "path": _rel(root, parsed.path),
            }
            if parsed.module in adapter_modules:
                adapter_consumers.append(row)
            elif parsed.module in legacy_owner_modules:
                legacy_internal_consumers.append(row)
            else:
                consumers.append(row)
        rows.append(
            {
                "legacy_module": legacy_module,
                "capability": capability,
                "production_consumer_count": len(consumers),
                "production_consumers": sorted(consumers, key=lambda row: row["path"]),
                "adapter_consumer_count": len(adapter_consumers),
                "adapter_consumers": sorted(adapter_consumers, key=lambda row: row["path"]),
                "legacy_internal_consumer_count": len(legacy_internal_consumers),
                "legacy_internal_consumers": sorted(legacy_internal_consumers, key=lambda row: row["path"]),
            }
        )
    return sorted(rows, key=lambda row: (row["capability"], row["legacy_module"]))


def _facade_and_adapters(root: Path, modules: list[ParsedModule]) -> dict[str, Any]:
    by_name = {parsed.module: parsed for parsed in modules}
    facade_rows: list[dict[str, Any]] = []
    for module, facade in FACADE_MODULES.items():
        parsed = by_name.get(module)
        facade_rows.append(
            {
                "module": module,
                "facade": facade,
                "present": parsed is not None,
                "path": _rel(root, parsed.path) if parsed else None,
                "classes": parsed.classes if parsed else [],
            }
        )
    adapter_rows: list[dict[str, Any]] = []
    for module, phase in ADAPTER_MODULES.items():
        parsed = by_name.get(module)
        adapter_rows.append(
            {
                "module": module,
                "phase": phase,
                "present": parsed is not None,
                "path": _rel(root, parsed.path) if parsed else None,
                "imports_app_api": any(imp.startswith("app.api") for imp in parsed.imports) if parsed else False,
            }
        )
    return {"facades": facade_rows, "adapters": adapter_rows}


def _module_implementations(root: Path, modules: list[ParsedModule]) -> dict[str, Any]:
    disabled = []
    concrete = []
    for parsed in modules:
        for cls in parsed.classes:
            row = {"class_name": cls, "module": parsed.module, "path": _rel(root, parsed.path)}
            if cls.startswith("Disabled") and cls.endswith("Module"):
                disabled.append(row)
            elif cls.endswith("ModuleImpl"):
                concrete.append(row)
    return {
        "disabled_modules": sorted(disabled, key=lambda row: (row["class_name"], row["path"])),
        "concrete_modules": sorted(concrete, key=lambda row: (row["class_name"], row["path"])),
        "concrete_facade_count": len(concrete),
        "disabled_facade_count": len(disabled),
    }


def _database_defaults(root: Path, modules: list[ParsedModule]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for parsed in modules:
        memory_default_count = sum(1 for literal in parsed.string_literals if literal == SQLITE_MEMORY_LITERAL)
        sqlite_mentions = [
            imp for imp in parsed.imports if imp == "sqlite3" or imp.startswith("sqlite3.")
        ]
        if memory_default_count or sqlite_mentions:
            rows.append(
                {
                    "module": parsed.module,
                    "path": _rel(root, parsed.path),
                    "imports_sqlite3": bool(sqlite_mentions),
                    "memory_default_count": memory_default_count,
                }
            )
    return sorted(rows, key=lambda row: row["path"])


def _critical_findings(root: Path, modules: list[ParsedModule]) -> list[dict[str, Any]]:
    impl = _module_implementations(root, modules)
    construction_classes = {row["class_name"] for row in impl["disabled_modules"] + impl["concrete_modules"]}
    return [
        {
            "issue_code": "PIR0-C01",
            "finding": "production factory defaults to disabled modules",
            "evidence": [
                row
                for row in _construction_sites(root, modules, construction_classes)
                if row["path"] == "agent/project_intelligence/factory.py"
                and row["class_name"].startswith("Disabled")
            ],
            "expected_followup_package": "PIR-2",
        },
        {
            "issue_code": "PIR0-C02",
            "finding": "coordinator active path builds twin context but returns baseline package",
            "evidence": [
                {
                    "path": "agent/project_intelligence/coordinator.py",
                    "module": "agent.project_intelligence.coordinator",
                }
            ],
            "expected_followup_package": "PIR-2",
        },
        {
            "issue_code": "PIR0-C03",
            "finding": "planner/generator/verification adapters exist but real Atlas API imports legacy consumers",
            "evidence": _production_entrypoints(root, modules),
            "expected_followup_package": "PIR-10",
        },
        {
            "issue_code": "PIR0-C04",
            "finding": "concrete DigitalTwinModuleImpl is absent",
            "evidence": [
                row for row in impl["concrete_modules"] if row["class_name"] == "DigitalTwinModuleImpl"
            ],
            "expected_followup_package": "PIR-1",
        },
        {
            "issue_code": "PIR0-C05",
            "finding": "concrete ConvergenceModuleImpl is absent",
            "evidence": [
                row for row in impl["concrete_modules"] if row["class_name"] == "ConvergenceModuleImpl"
            ],
            "expected_followup_package": "PIR-1",
        },
        {
            "issue_code": "PIR0-C06",
            "finding": "in-memory persistence defaults remain in current stores",
            "evidence": [row for row in _database_defaults(root, modules) if row["memory_default_count"]],
            "expected_followup_package": "PIR-1",
        },
    ]


def build_inventory(root: Path) -> dict[str, Any]:
    """Build a deterministic inventory from current repository source."""
    root = root.resolve()
    modules = [_parse_module(root, path) for path in _iter_python_files(root)]
    module_impls = _module_implementations(root, modules)
    class_names = {row["class_name"] for row in module_impls["disabled_modules"] + module_impls["concrete_modules"]}
    inventory = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source": "python_ast_current_checkout",
        "repository_root": root.name,
        "production_entrypoints": _production_entrypoints(root, modules),
        "legacy_consumers": _legacy_consumers(root, modules),
        "project_intelligence": _facade_and_adapters(root, modules),
        "module_implementations": module_impls,
        "construction_sites": _construction_sites(root, modules, class_names),
        "database_defaults": _database_defaults(root, modules),
        "critical_findings": _critical_findings(root, modules),
        "parse_errors": [
            {"path": _rel(root, parsed.path), "error": parsed.parse_error}
            for parsed in modules
            if parsed.parse_error
        ],
    }
    inventory["summary"] = {
        "production_entrypoint_count": len(inventory["production_entrypoints"]),
        "legacy_production_consumer_count": sum(
            row["production_consumer_count"] for row in inventory["legacy_consumers"]
        ),
        "facade_module_count": sum(1 for row in inventory["project_intelligence"]["facades"] if row["present"]),
        "adapter_module_count": sum(1 for row in inventory["project_intelligence"]["adapters"] if row["present"]),
        "disabled_facade_count": module_impls["disabled_facade_count"],
        "concrete_facade_count": module_impls["concrete_facade_count"],
        "critical_finding_count": len(inventory["critical_findings"]),
    }
    return inventory


def write_inventory(root: Path, output: Path) -> dict[str, Any]:
    inventory = build_inventory(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return inventory

