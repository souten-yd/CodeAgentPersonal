from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import Field

from app.atlas.play.contracts import (
    EnvironmentSpec,
    LaunchKind,
    LaunchProfile,
    StrictContractModel,
)
from app.atlas.play.workspace_policy import WorkspacePermission, decide_workspace_access


ENVIRONMENT_SCHEMA_VERSION = "atlas.play.environment.v1"
_SAFE_ARG_RE = re.compile(r"^[\w./:@=,+-]+$")
_SAFE_ENV_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")


class PortAllocationContract(StrictContractModel):
    schema_version: str = ENVIRONMENT_SCHEMA_VERSION
    host: str = "127.0.0.1"
    port: int = 0
    loopback_only: bool = True
    expose_directly: bool = False


class StructuredLaunchAdapter(StrictContractModel):
    schema_version: str = ENVIRONMENT_SCHEMA_VERSION
    status: str
    profile_id: str
    kind: LaunchKind
    executable: str = ""
    argv: list[str] = Field(default_factory=list)
    working_directory: str = "."
    environment: dict[str, str] = Field(default_factory=dict)
    port: PortAllocationContract = Field(default_factory=PortAllocationContract)
    missing_dependencies: list[str] = Field(default_factory=list)
    diagnostics: list[str] = Field(default_factory=list)
    host_mutation_allowed: bool = False
    execution_started: bool = False


class CompositeValidationResult(StrictContractModel):
    schema_version: str = ENVIRONMENT_SCHEMA_VERSION
    valid: bool
    startup_order: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


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


def _safe_working_directory(project_root: Path, relative_path: str) -> str | None:
    decision = decide_workspace_access(
        project_root=project_root,
        relative_path=relative_path or ".",
        permission=WorkspacePermission.READ,
        allow_root=True,
    )
    if not decision.allowed:
        return None
    path = Path(decision.resolved_path)
    return path.relative_to(project_root).as_posix() if path != project_root else "."


def _validate_args(args: list[str]) -> list[str]:
    cleaned: list[str] = []
    for arg in args[:32]:
        value = str(arg or "").strip()
        if not value or len(value) > 128 or not _SAFE_ARG_RE.fullmatch(value):
            raise ValueError("disallowed_argument")
        cleaned.append(value)
    return cleaned


def _validate_environment_keys(keys: list[str]) -> dict[str, str]:
    env: dict[str, str] = {}
    for key in keys[:64]:
        value = str(key or "").strip()
        if not _SAFE_ENV_KEY_RE.fullmatch(value) or value in {"PATH", "PYTHONPATH", "NODE_OPTIONS"}:
            raise ValueError("disallowed_environment_key")
        env[value] = ""
    return env


def resolve_python_environment(project_root: str | Path) -> EnvironmentSpec:
    root = Path(project_root).expanduser().resolve()
    candidates = [
        root / ".venv" / "Scripts" / "python.exe",
        root / "venv" / "Scripts" / "python.exe",
        root / ".venv" / "bin" / "python",
        root / "venv" / "bin" / "python",
    ]
    python = next((str(path) for path in candidates if path.exists()), "python")
    manifests = [name for name in ("requirements.txt", "pyproject.toml", "Pipfile") if (root / name).exists()]
    missing = ["python_environment_not_local"] if manifests and python == "python" else []
    return EnvironmentSpec(
        python_executable=python,
        missing_dependencies=missing,
        host_mutation_allowed=False,
        allowed_environment={},
    )


def resolve_node_environment(project_root: str | Path) -> EnvironmentSpec:
    root = Path(project_root).expanduser().resolve()
    package_json = root / "package.json"
    missing: list[str] = []
    package_manager = ""
    if not package_json.exists():
        missing.append("package_json_missing")
    else:
        try:
            json.loads(package_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            missing.append("package_json_invalid")
    if (root / "pnpm-lock.yaml").exists():
        package_manager = "pnpm"
    elif (root / "yarn.lock").exists():
        package_manager = "yarn"
    elif (root / "package-lock.json").exists():
        package_manager = "npm"
    else:
        package_manager = "npm"
    return EnvironmentSpec(
        node_executable="node",
        package_manager=package_manager,
        missing_dependencies=missing,
        host_mutation_allowed=False,
        allowed_environment={},
    )


def _module_ref(entrypoint: str) -> str:
    path = Path(entrypoint)
    return ".".join(path.with_suffix("").parts) + ":app"


def build_structured_launch_adapter(project_root: str | Path, profile: LaunchProfile) -> StructuredLaunchAdapter:
    root = Path(project_root).expanduser().resolve()
    diagnostics: list[str] = []
    missing: list[str] = []
    try:
        args = _validate_args(profile.args)
        env = _validate_environment_keys(profile.environment_keys)
    except ValueError as exc:
        return StructuredLaunchAdapter(
            status="blocked",
            profile_id=profile.profile_id,
            kind=profile.kind,
            missing_dependencies=[],
            diagnostics=[str(exc)],
        )
    workdir = _safe_working_directory(root, profile.working_directory)
    if workdir is None:
        return StructuredLaunchAdapter(status="blocked", profile_id=profile.profile_id, kind=profile.kind, diagnostics=["working_directory_unsafe"])
    entry = profile.entrypoint or ""
    if profile.kind != LaunchKind.COMPOSITE and _safe_existing_file(root, entry) is None and profile.kind != LaunchKind.NPM_SCRIPT:
        missing.append("entrypoint_missing_or_unsafe")

    py_env = resolve_python_environment(root)
    node_env = resolve_node_environment(root)
    executable = ""
    argv: list[str] = []
    if profile.kind == LaunchKind.STATIC_WEB:
        executable = "atlas_static_server"
        argv = ["serve-static", entry]
    elif profile.kind == LaunchKind.PYTHON_SCRIPT:
        executable = py_env.python_executable or "python"
        argv = [executable, entry, *args]
        missing.extend(py_env.missing_dependencies)
    elif profile.kind == LaunchKind.PYTHON_ASGI:
        executable = py_env.python_executable or "python"
        argv = [executable, "-m", "uvicorn", _module_ref(entry), "--host", "127.0.0.1", "--port", "{PORT}", *args]
        missing.extend(py_env.missing_dependencies)
    elif profile.kind == LaunchKind.PYTHON_WSGI:
        executable = py_env.python_executable or "python"
        argv = [executable, "-m", "waitress", "--listen=127.0.0.1:{PORT}", _module_ref(entry), *args]
        missing.extend(py_env.missing_dependencies)
    elif profile.kind == LaunchKind.STREAMLIT:
        executable = py_env.python_executable or "python"
        argv = [executable, "-m", "streamlit", "run", entry, "--server.address", "127.0.0.1", "--server.port", "{PORT}", *args]
        missing.extend(py_env.missing_dependencies)
    elif profile.kind == LaunchKind.DJANGO:
        executable = py_env.python_executable or "python"
        argv = [executable, entry, "runserver", "127.0.0.1:{PORT}", *args]
        missing.extend(py_env.missing_dependencies)
    elif profile.kind == LaunchKind.NODE_SCRIPT:
        executable = node_env.node_executable or "node"
        argv = [executable, entry, *args]
        missing.extend(node_env.missing_dependencies)
    elif profile.kind in {LaunchKind.NPM_SCRIPT, LaunchKind.VITE, LaunchKind.NEXT}:
        executable = node_env.package_manager or "npm"
        script = args[0] if profile.kind == LaunchKind.NPM_SCRIPT and args else "dev"
        argv = [executable, "run", script]
        if profile.kind == LaunchKind.VITE:
            argv.extend(["--", "--host", "127.0.0.1", "--port", "{PORT}"])
        elif profile.kind == LaunchKind.NEXT:
            argv.extend(["--", "--hostname", "127.0.0.1", "--port", "{PORT}"])
        missing.extend(node_env.missing_dependencies)
    elif profile.kind == LaunchKind.COMPOSITE:
        executable = "atlas_composite_launcher"
        argv = ["composite", *profile.depends_on]
    status = "missing_dependency" if missing else "ready"
    return StructuredLaunchAdapter(
        status=status,
        profile_id=profile.profile_id,
        kind=profile.kind,
        executable=executable,
        argv=argv,
        working_directory=workdir,
        environment=env,
        missing_dependencies=list(dict.fromkeys(missing)),
        diagnostics=diagnostics,
    )


def validate_composite_launch_profiles(profiles: list[LaunchProfile]) -> CompositeValidationResult:
    by_id = {profile.profile_id: profile for profile in profiles}
    if len(by_id) != len(profiles):
        return CompositeValidationResult(valid=False, errors=["duplicate_profile_id"])
    errors: list[str] = []
    for profile in profiles:
        for dep in profile.depends_on:
            if dep not in by_id:
                errors.append(f"unknown_dependency:{profile.profile_id}:{dep}")
    if errors:
        return CompositeValidationResult(valid=False, errors=errors)
    visiting: set[str] = set()
    visited: set[str] = set()
    order: list[str] = []

    def visit(profile_id: str) -> None:
        if profile_id in visited:
            return
        if profile_id in visiting:
            errors.append(f"dependency_cycle:{profile_id}")
            return
        visiting.add(profile_id)
        for dep in by_id[profile_id].depends_on:
            visit(dep)
        visiting.remove(profile_id)
        visited.add(profile_id)
        order.append(profile_id)

    for profile_id in by_id:
        visit(profile_id)
    return CompositeValidationResult(valid=not errors, startup_order=order if not errors else [], errors=errors)
