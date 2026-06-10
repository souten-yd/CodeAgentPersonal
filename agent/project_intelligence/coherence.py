"""Coherent multi-file generation and consistency validation (PI-21).

Validates a generated multi-file slice against the Blueprint manifest and itself, turning
each mismatch into a typed gap with a recovery policy. Missing dependency and missing file
have distinct recovery policies; local repair is preferred before a Blueprint revision; and
a placeholder file never counts as completion. Pure (stdlib only).
"""

from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from agent.architecture_blueprint.contracts import BlueprintRevision
from agent.project_intelligence.contracts import GapSummary

# Gap codes.
IMPORTS_UNRESOLVED = "imports_unresolved"
ASSET_MISSING = "asset_missing"
API_MISMATCH = "api_mismatch"
DEPENDENCY_MISSING = "dependency_missing"
ENTRYPOINT_MISSING = "entrypoint_missing"
COMMAND_MISSING = "command_missing"
PATH_NOT_IN_MANIFEST = "path_not_in_manifest"
PLACEHOLDER_NOT_COMPLETE = "placeholder_not_complete"
TESTS_USE_UNKNOWN_INTERFACE = "tests_use_unknown_interface"

# Recovery policies (distinct per failure class).
LOCAL_REPAIR = "local_repair"
ADD_DEPENDENCY = "add_dependency"
CREATE_MISSING_FILE = "create_missing_file"
BLUEPRINT_REVISION = "blueprint_revision"

_AUX_FILES = {"__init__.py"}
_PLACEHOLDER_RE = re.compile(r"^\s*(pass|\.\.\.|#.*|\"\"\".*\"\"\"|'''.*''')?\s*$", re.S)
_TODO_RE = re.compile(r"\b(TODO|FIXME|NotImplemented|raise NotImplementedError)\b")
_ASSET_RE = re.compile(r"""(?:src|href)\s*=\s*['"]([^'":#?]+)['"]""")
_VUE_IMPORT_RE = re.compile(r"""import\s+(?:[\w*\s{},]+?)\s+from\s+['"](\.[^'"]+)['"]""")
_FETCH_RE = re.compile(r"""fetch\(\s*[`'"]([^`'"]+)['"`]""")
_AXIOS_RE = re.compile(r"""axios\.(get|post|put|delete|patch)\(\s*[`'"]([^`'"]+)['"`]""")
_ROUTE_DEC_RE = re.compile(r"""@\w+\.(get|post|put|delete|patch)\(\s*['"]([^'"]+)['"]""")

_STDLIB = set(getattr(sys, "stdlib_module_names", set())) | {"__future__"}


@dataclass
class CoherenceGap:
    code: str
    message: str
    refs: list[str] = field(default_factory=list)
    recovery_policy: str = LOCAL_REPAIR


@dataclass
class CoherenceReport:
    coherent: bool
    gaps: list[CoherenceGap] = field(default_factory=list)
    unexpected_files: list[str] = field(default_factory=list)
    placeholder_files: list[str] = field(default_factory=list)

    def recommended_first_action(self) -> str:
        """Prefer local repair / dependency / file creation before a Blueprint revision."""
        order = [LOCAL_REPAIR, ADD_DEPENDENCY, CREATE_MISSING_FILE, BLUEPRINT_REVISION]
        present = {g.recovery_policy for g in self.gaps}
        for policy in order:
            if policy in present:
                return policy
        return "none"


def _module_to_path(module: str) -> str:
    return module.replace(".", "/") + ".py"


def _check_python_imports(files: dict[str, str], dependencies: set[str], gaps: list[CoherenceGap]) -> None:
    generated = set(files)
    for rel, content in files.items():
        if not rel.endswith(".py"):
            continue
        try:
            tree = ast.parse(content)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            mods: list[str] = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                mods = [node.module]
            for mod in mods:
                top = mod.split(".")[0]
                candidate = _module_to_path(mod)
                pkg_init = mod.replace(".", "/") + "/__init__.py"
                if candidate in generated or pkg_init in generated:
                    continue  # local import resolves
                if top in _STDLIB:
                    continue
                if top in dependencies:
                    continue
                # Unresolved: a local-looking import missing a file vs a third-party dep.
                if candidate.startswith(tuple(sorted({p.split('/')[0] + '/' for p in generated}))):
                    gaps.append(CoherenceGap(IMPORTS_UNRESOLVED, f"{rel}: unresolved local import {mod!r}",
                                             [rel, candidate], CREATE_MISSING_FILE))
                else:
                    gaps.append(CoherenceGap(DEPENDENCY_MISSING, f"{rel}: dependency {top!r} not in manifest",
                                             [rel, top], ADD_DEPENDENCY))


def _check_assets(files: dict[str, str], gaps: list[CoherenceGap]) -> None:
    generated = set(files)
    for rel, content in files.items():
        if not (rel.endswith(".html") or rel.endswith(".vue")):
            continue
        base = Path(rel).parent
        refs = _ASSET_RE.findall(content) + _VUE_IMPORT_RE.findall(content)
        for ref in refs:
            if ref.startswith(("http://", "https://", "//", "data:")):
                continue
            target = (base / ref).as_posix().lstrip("./")
            norm = Path(target).as_posix()
            if norm not in generated and ref.lstrip("./") not in generated:
                gaps.append(CoherenceGap(ASSET_MISSING, f"{rel}: referenced asset {ref!r} missing",
                                         [rel, ref], CREATE_MISSING_FILE))


def _check_api_agreement(files: dict[str, str], gaps: list[CoherenceGap]) -> None:
    backend_routes: set[str] = set()
    for rel, content in files.items():
        if rel.endswith(".py"):
            for method, path in _ROUTE_DEC_RE.findall(content):
                backend_routes.add(path)
    for rel, content in files.items():
        if rel.endswith((".js", ".jsx", ".ts", ".tsx", ".vue")):
            frontend = [m for m in _FETCH_RE.findall(content)]
            frontend += [p for _, p in _AXIOS_RE.findall(content)]
            for route in frontend:
                path = route.split("?")[0]
                if backend_routes and path not in backend_routes:
                    gaps.append(CoherenceGap(API_MISMATCH,
                                             f"{rel}: frontend calls {path!r} with no matching backend route",
                                             [rel, path], LOCAL_REPAIR))


def _check_manifest_membership(files: dict[str, str], revision: BlueprintRevision,
                               gaps: list[CoherenceGap], unexpected: list[str]) -> None:
    manifest_paths = set()
    for el in revision.elements:
        for r in el.expected_actual_refs:
            if r.startswith("file://"):
                manifest_paths.add(r[len("file://"):])
    for rel in files:
        if rel in manifest_paths:
            continue
        if Path(rel).name in _AUX_FILES:
            continue  # aux files are classified as allowed, not gaps
        unexpected.append(rel)
        gaps.append(CoherenceGap(PATH_NOT_IN_MANIFEST, f"generated path {rel!r} not in Blueprint manifest",
                                 [rel], BLUEPRINT_REVISION))


def _check_execution_contracts(revision: BlueprintRevision, gaps: list[CoherenceGap]) -> None:
    types = {e.element_type for e in revision.elements}
    if revision.scope == "full_project":
        if "entrypoint" not in types:
            gaps.append(CoherenceGap(ENTRYPOINT_MISSING, "no entrypoint element", [], LOCAL_REPAIR))
        commands = {}
        for e in revision.elements:
            commands.update({k: v for k, v in (e.properties or {}).items()
                             if k in ("build_command", "start_command", "test_command") and v})
        for needed in ("build_command", "start_command", "test_command"):
            if needed not in commands:
                gaps.append(CoherenceGap(COMMAND_MISSING, f"missing {needed}", [], LOCAL_REPAIR))


def _check_placeholders(files: dict[str, str], gaps: list[CoherenceGap], placeholders: list[str]) -> None:
    for rel, content in files.items():
        if not rel.endswith(".py"):
            continue
        if Path(rel).name in _AUX_FILES:
            continue  # an empty __init__.py is a legitimate package marker, not a placeholder
        stripped = content.strip()
        is_placeholder = (not stripped) or _TODO_RE.search(content) or all(
            _PLACEHOLDER_RE.match(line) for line in content.splitlines() if line.strip()
        ) and "def " not in content and "class " not in content
        if is_placeholder:
            placeholders.append(rel)
            gaps.append(CoherenceGap(PLACEHOLDER_NOT_COMPLETE, f"{rel}: placeholder content is not completion",
                                     [rel], LOCAL_REPAIR))


def check_coherence(
    *,
    revision: BlueprintRevision,
    generated_files: dict[str, str],
    dependencies: set[str] | None = None,
) -> CoherenceReport:
    gaps: list[CoherenceGap] = []
    unexpected: list[str] = []
    placeholders: list[str] = []
    deps = dependencies or set()

    _check_python_imports(generated_files, deps, gaps)
    _check_assets(generated_files, gaps)
    _check_api_agreement(generated_files, gaps)
    _check_manifest_membership(generated_files, revision, gaps, unexpected)
    _check_execution_contracts(revision, gaps)
    _check_placeholders(generated_files, gaps, placeholders)

    return CoherenceReport(coherent=not gaps, gaps=gaps, unexpected_files=sorted(unexpected),
                           placeholder_files=sorted(placeholders))


def to_convergence_gaps(report: CoherenceReport) -> list[GapSummary]:
    """Coherence gaps become typed Convergence gaps."""
    return [
        GapSummary(gap_id=f"coh:{i}", description=f"{g.code}: {g.message}", mandatory=True,
                   missing_refs=g.refs)
        for i, g in enumerate(report.gaps)
    ]
