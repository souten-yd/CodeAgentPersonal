from __future__ import annotations

import ast
import json
import posixpath
import re
from collections import deque
from pathlib import Path
from typing import Any

from pydantic import Field

from app.atlas.play.contracts import LaunchKind, PlayRequestSource, PlayTarget, StrictContractModel
from app.atlas.play.workspace_policy import WorkspacePermission, decide_workspace_access


TARGET_DISCOVERY_SCHEMA_VERSION = "atlas.play.target_discovery.v1"

_HTML_ATTR_RE = re.compile(r"""(?:src|href)\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
_CSS_IMPORT_RE = re.compile(r"""@import\s+(?:url\()?["']?([^"')]+)["']?\)?""", re.IGNORECASE)
_CSS_URL_RE = re.compile(r"""url\(["']?([^"')]+)["']?\)""", re.IGNORECASE)
_JS_IMPORT_RE = re.compile(
    r"""(?:import\s+(?:[^'"]+\s+from\s+)?|import\s*\(|require\s*\()\s*["']([^"']+)["']""",
    re.IGNORECASE,
)
_REMOTE_OR_SPECIAL_RE = re.compile(r"^(?:[a-z][a-z0-9+.-]*:|//|#|data:)", re.IGNORECASE)


class PlayLaunchCandidate(StrictContractModel):
    schema_version: str = TARGET_DISCOVERY_SCHEMA_VERSION
    entrypoint: str
    launch_kind: LaunchKind
    label: str
    reason: str = ""


class DependencyGraph(StrictContractModel):
    schema_version: str = TARGET_DISCOVERY_SCHEMA_VERSION
    entrypoint: str = ""
    files: list[str] = Field(default_factory=list)
    edges: list[dict[str, str]] = Field(default_factory=list)
    missing: list[dict[str, str]] = Field(default_factory=list)
    diagnostics: list[str] = Field(default_factory=list)


class PlayTargetResolutionRequest(StrictContractModel):
    schema_version: str = TARGET_DISCOVERY_SCHEMA_VERSION
    project_id: str = Field(min_length=1)
    source: PlayRequestSource
    command_text: str = ""
    current_editor_path: str = ""
    selected_file_path: str = ""
    last_target_path: str = ""


class PlayTargetResolution(StrictContractModel):
    schema_version: str = TARGET_DISCOVERY_SCHEMA_VERSION
    status: str
    source: PlayRequestSource
    project_id: str
    target: PlayTarget | None = None
    candidates: list[PlayLaunchCandidate] = Field(default_factory=list)
    dependency_graph: DependencyGraph = Field(default_factory=DependencyGraph)
    diagnostics: list[str] = Field(default_factory=list)


def _read_text(path: Path, max_chars: int = 300_000) -> str:
    return path.read_text(encoding="utf-8", errors="replace")[:max_chars]


def _is_external_ref(value: str) -> bool:
    return bool(_REMOTE_OR_SPECIAL_RE.match(str(value or "").strip()))


def _safe_existing_file(project_root: Path, relative_path: str) -> Path | None:
    decision = decide_workspace_access(
        project_root=project_root,
        relative_path=relative_path,
        permission=WorkspacePermission.READ,
    )
    if not decision.allowed:
        return None
    path = Path(decision.resolved_path)
    return path if path.exists() and path.is_file() else None


def _resolve_dependency(project_root: Path, owner_rel: str, raw_ref: str) -> tuple[str, Path | None, str]:
    ref = str(raw_ref or "").split("?", 1)[0].split("#", 1)[0].strip()
    if not ref or _is_external_ref(ref):
        return "", None, "external_or_empty"
    base = Path(owner_rel).parent
    rel = posixpath.normpath((base / ref).as_posix())
    if rel == "." or rel.startswith("../") or rel == "..":
        return ref, None, "path_escape"
    candidates = [rel]
    if not Path(rel).suffix:
        candidates.extend([f"{rel}.js", f"{rel}.mjs", f"{rel}.ts", f"{rel}.css", f"{rel}.json", f"{rel}/index.js"])
    for candidate in candidates:
        path = _safe_existing_file(project_root, candidate)
        if path is not None:
            return candidate, path, ""
    return rel, None, "missing_dependency"


def _html_refs(text: str) -> list[str]:
    return [match.group(1) for match in _HTML_ATTR_RE.finditer(text)]


def _css_refs(text: str) -> list[str]:
    return [match.group(1) for match in _CSS_IMPORT_RE.finditer(text)] + [
        match.group(1) for match in _CSS_URL_RE.finditer(text)
    ]


def _js_refs(text: str) -> list[str]:
    return [match.group(1) for match in _JS_IMPORT_RE.finditer(text)]


def _python_refs(project_root: Path, owner_rel: str, text: str) -> list[str]:
    refs: list[str] = []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return refs
    owner_dir = Path(owner_rel).parent
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name.split(".", 1)[0] for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module.split(".", 1)[0]]
        for name in names:
            for rel in ((owner_dir / f"{name}.py").as_posix(), f"{name}.py", f"{name}/__init__.py"):
                if _safe_existing_file(project_root, rel):
                    refs.append(rel)
                    break
    return refs


def discover_dependency_graph(project_root: str | Path, entrypoint: str) -> DependencyGraph:
    root = Path(project_root).expanduser().resolve()
    entry = _safe_existing_file(root, entrypoint)
    if entry is None:
        return DependencyGraph(
            entrypoint=entrypoint,
            diagnostics=["entrypoint_missing_or_unsafe"],
            missing=[{"from": "", "ref": entrypoint, "reason": "entrypoint_missing_or_unsafe"}],
        )
    start_rel = entry.relative_to(root).as_posix()
    files: list[str] = []
    edges: list[dict[str, str]] = []
    missing: list[dict[str, str]] = []
    queue: deque[str] = deque([start_rel])
    seen: set[str] = set()
    while queue and len(seen) < 500:
        rel = queue.popleft()
        if rel in seen:
            continue
        seen.add(rel)
        files.append(rel)
        path = _safe_existing_file(root, rel)
        if path is None:
            continue
        text = _read_text(path)
        suffix = path.suffix.lower()
        refs: list[str] = []
        if suffix in {".html", ".htm"}:
            refs = _html_refs(text)
        elif suffix in {".css"}:
            refs = _css_refs(text)
        elif suffix in {".js", ".mjs", ".ts", ".jsx", ".tsx"}:
            refs = _js_refs(text)
        elif suffix == ".py":
            refs = _python_refs(root, rel, text)
        for ref in refs:
            dep_rel, dep_path, reason = _resolve_dependency(root, rel, ref)
            if not dep_rel:
                continue
            if dep_path is None:
                missing.append({"from": rel, "ref": ref, "resolved": dep_rel, "reason": reason})
                continue
            edges.append({"from": rel, "to": dep_rel})
            if dep_rel not in seen:
                queue.append(dep_rel)
    diagnostics = ["dependency_limit_reached"] if queue else []
    return DependencyGraph(entrypoint=start_rel, files=files, edges=edges, missing=missing, diagnostics=diagnostics)


def detect_launch_candidates(project_root: str | Path) -> list[PlayLaunchCandidate]:
    root = Path(project_root).expanduser().resolve()
    candidates: list[PlayLaunchCandidate] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        rel = path.relative_to(root).as_posix()
        if _safe_existing_file(root, rel) is None:
            continue
        suffix = path.suffix.lower()
        if suffix in {".html", ".htm"}:
            candidates.append(PlayLaunchCandidate(entrypoint=rel, launch_kind=LaunchKind.STATIC_WEB, label=path.name, reason="html_entrypoint"))
        elif suffix == ".py" and path.name not in {"__init__.py"}:
            text = _read_text(path, max_chars=50_000)
            kind = LaunchKind.PYTHON_ASGI if "FastAPI(" in text or "Starlette(" in text else LaunchKind.PYTHON_SCRIPT
            candidates.append(PlayLaunchCandidate(entrypoint=rel, launch_kind=kind, label=path.name, reason="python_entrypoint"))
        elif path.name == "package.json":
            try:
                package = json.loads(_read_text(path, max_chars=100_000))
            except json.JSONDecodeError:
                continue
            scripts = package.get("scripts") if isinstance(package, dict) else {}
            deps = {**(package.get("dependencies") or {}), **(package.get("devDependencies") or {})} if isinstance(package, dict) else {}
            if isinstance(scripts, dict) and scripts:
                text = " ".join(str(value) for value in scripts.values()).lower()
                kind = LaunchKind.VITE if "vite" in text or "vite" in deps else LaunchKind.NEXT if "next" in text or "next" in deps else LaunchKind.NPM_SCRIPT
                candidates.append(PlayLaunchCandidate(entrypoint=rel, launch_kind=kind, label="package.json", reason="package_scripts"))
    return candidates[:100]


def _explicit_from_command(command_text: str) -> str:
    text = str(command_text or "").strip()
    if not text.lower().startswith("/play"):
        return ""
    return text[5:].strip()


def resolve_play_target(project_root: str | Path, request: PlayTargetResolutionRequest) -> PlayTargetResolution:
    root = Path(project_root).expanduser().resolve()
    diagnostics: list[str] = []
    explicit = _explicit_from_command(request.command_text)
    ordered = [
        ("explicit_entrypoint", explicit),
        ("current_editor_path", request.current_editor_path),
        ("selected_file_path", request.selected_file_path),
        ("last_target_path", request.last_target_path),
    ]
    for source_name, rel in ordered:
        if not str(rel or "").strip():
            continue
        path = _safe_existing_file(root, rel)
        if path is None:
            diagnostics.append(f"{source_name}_missing_or_unsafe")
            continue
        graph = discover_dependency_graph(root, path.relative_to(root).as_posix())
        target = PlayTarget(
            project_id=request.project_id,
            work_root=str(root),
            entrypoint=path.relative_to(root).as_posix(),
            related_files=graph.files,
            detected_launch_kinds=[candidate.launch_kind for candidate in detect_launch_candidates(root) if candidate.entrypoint == path.relative_to(root).as_posix()],
            diagnostics=[*diagnostics, *graph.diagnostics],
        )
        return PlayTargetResolution(
            status="resolved",
            source=request.source,
            project_id=request.project_id,
            target=target,
            candidates=[],
            dependency_graph=graph,
            diagnostics=diagnostics,
        )
    candidates = detect_launch_candidates(root)
    if len(candidates) == 1:
        graph = discover_dependency_graph(root, candidates[0].entrypoint)
        target = PlayTarget(
            project_id=request.project_id,
            work_root=str(root),
            entrypoint=candidates[0].entrypoint,
            related_files=graph.files,
            detected_launch_kinds=[candidates[0].launch_kind],
            diagnostics=graph.diagnostics,
        )
        return PlayTargetResolution(
            status="resolved",
            source=request.source,
            project_id=request.project_id,
            target=target,
            candidates=candidates,
            dependency_graph=graph,
        )
    if candidates:
        return PlayTargetResolution(
            status="needs_selection",
            source=request.source,
            project_id=request.project_id,
            candidates=candidates,
            diagnostics=[*diagnostics, "multiple_candidates"],
        )
    return PlayTargetResolution(
        status="unsupported",
        source=request.source,
        project_id=request.project_id,
        diagnostics=[*diagnostics, "no_launch_candidates"],
    )
