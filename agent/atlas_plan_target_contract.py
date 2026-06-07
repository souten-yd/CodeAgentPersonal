from __future__ import annotations

import copy
import re
from pathlib import PurePosixPath
from typing import Any, Literal

from pydantic import BaseModel, Field


PLAN_TARGET_CONTRACT_SCHEMA_VERSION = "plan_patch_contract_v1"

PatchTaskKind = Literal[
    "code_change",
    "configuration_change",
    "documentation_change",
    "test_change",
    "structural_change",
    "mixed_change",
]

PlanOperationType = Literal[
    "create_file",
    "modify_file",
    "delete_file",
    "create_directory",
    "remove_directory",
    "create_structure",
]

PATCH_TASK_KINDS = {
    "code_change",
    "configuration_change",
    "documentation_change",
    "test_change",
    "structural_change",
    "mixed_change",
}
PLAN_OPERATION_TYPES = {
    "create_file",
    "modify_file",
    "delete_file",
    "create_directory",
    "remove_directory",
    "create_structure",
}
UNSUPPORTED_OPERATION_TYPES = {"remove_directory"}
KNOWN_EXTENSIONLESS_FILES = {
    "dockerfile",
    "makefile",
    "license",
    "readme",
    "procfile",
    "gemfile",
    "jenkinsfile",
}
DIRECTORY_INTENT_RE = re.compile(
    r"\b(directory|directories|folder|folders|scaffold|structure|source tree|package hierarchy)\b"
    r"|ディレクトリ|フォルダ|構造",
    re.IGNORECASE,
)
CONFIG_NAMES = {
    "package.json",
    "requirements.txt",
    "pyproject.toml",
    "dockerfile",
    "docker-compose.yml",
    "environment.yml",
    "poetry.lock",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
}


class PlanOperation(BaseModel):
    type: PlanOperationType
    path: str = ""
    paths: list[str] = Field(default_factory=list)
    reason: str = ""


class TargetNormalizationResult(BaseModel):
    schema_version: str = PLAN_TARGET_CONTRACT_SCHEMA_VERSION
    patch_task_kind: PatchTaskKind = "code_change"
    target_files: list[str] = Field(default_factory=list)
    target_directories: list[str] = Field(default_factory=list)
    operations: list[PlanOperation] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    normalization_diagnostics: list[dict[str, Any]] = Field(default_factory=list)
    needs_revision: bool = False


class TargetValidationResult(BaseModel):
    ok: bool = True
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    unsupported_operations: list[str] = Field(default_factory=list)


class StructuralMaterializationResult(BaseModel):
    status: str = "not_required"
    patch_target_files: list[str] = Field(default_factory=list)
    file_changes: list[dict[str, Any]] = Field(default_factory=list)
    normalized_target_files: list[str] = Field(default_factory=list)
    normalized_target_directories: list[str] = Field(default_factory=list)
    normalized_operations: list[dict[str, Any]] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    diagnostics: list[dict[str, Any]] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)


def normalize_plan_targets(
    *,
    title: str = "",
    description: str = "",
    goal: str = "",
    action_type: Any = "",
    patch_task_kind: Any = "",
    target_files: Any = None,
    target_directories: Any = None,
    operations: Any = None,
    assumptions: Any = None,
    existing_file_paths: set[str] | None = None,
    existing_directory_paths: set[str] | None = None,
) -> TargetNormalizationResult:
    text = " ".join(str(v or "") for v in (title, description, goal, action_type))
    diagnostics: list[dict[str, Any]] = []
    existing_files = {_clean_path(p) for p in (existing_file_paths or set()) if _clean_path(p)}
    existing_dirs = {_clean_path(p) for p in (existing_directory_paths or set()) if _clean_path(p)}
    files: list[str] = []
    directories: list[str] = []

    explicit_dirs = [_clean_path(p) for p in _as_str_list(target_directories)]
    for path in explicit_dirs:
        if not path:
            continue
        if not _is_safe_rel_path(path):
            diagnostics.append(_diag("unsafe_path", path, "target_directories"))
            continue
        directories.append(path)

    raw_files = [_clean_path(p) for p in _as_str_list(target_files)]
    raw_file_set = {p for p in raw_files if p}
    child_parent_dirs = _parents_named_by_children(raw_file_set)
    for path in raw_files:
        if not path:
            continue
        if not _is_safe_rel_path(path):
            diagnostics.append(_diag("unsafe_path", path, "target_files"))
            continue
        if path in directories:
            continue
        if _should_treat_as_directory(
            path,
            text=text,
            child_parent_dirs=child_parent_dirs,
            existing_files=existing_files,
            existing_dirs=existing_dirs,
        ):
            directories.append(path)
            diagnostics.append(_diag("moved_target_file_to_directory", path, "target_files"))
        else:
            files.append(path)

    files = _dedup(files)
    directories = [p for p in _dedup(directories) if p not in files]
    normalized_ops, op_diags = _normalize_operations(operations)
    diagnostics.extend(op_diags)
    inferred_kind = _normalize_patch_task_kind(patch_task_kind) or _infer_patch_task_kind(
        files=files,
        directories=directories,
        text=text,
    )
    op_types = {op.type for op in normalized_ops}
    if "remove_directory" in op_types:
        diagnostics.append({"reason": "unsupported_operation", "operation_type": "remove_directory"})

    if not normalized_ops:
        normalized_ops = _build_operations(files=files, directories=directories, action_type=str(action_type or ""))

    needs_revision = False
    if any(d.get("reason") == "unsafe_path" for d in diagnostics):
        needs_revision = True
    if any(d.get("reason") == "unsupported_operation" for d in diagnostics):
        needs_revision = True
    if DIRECTORY_INTENT_RE.search(text) and not files and not directories:
        diagnostics.append({"reason": "ambiguous_structural_target", "source": "intent"})
        needs_revision = True

    return TargetNormalizationResult(
        patch_task_kind=inferred_kind,
        target_files=files,
        target_directories=directories,
        operations=normalized_ops,
        assumptions=_dedup(_as_str_list(assumptions)),
        normalization_diagnostics=diagnostics,
        needs_revision=needs_revision,
    )


def normalize_plan_for_review(plan: Any, *, repository_context: str = "") -> Any:
    """Return a normalized copy of the final adopted plan before review."""
    payload = _model_dump(plan)
    existing_files, existing_dirs = _repo_paths_from_context(repository_context)
    top = normalize_plan_targets(
        title=str(payload.get("user_goal") or ""),
        description=str(payload.get("requirement_summary") or ""),
        goal=str(payload.get("original_user_request") or ""),
        action_type="",
        patch_task_kind=payload.get("patch_task_kind"),
        target_files=payload.get("target_files"),
        target_directories=payload.get("target_directories"),
        operations=payload.get("operations"),
        assumptions=payload.get("assumptions"),
        existing_file_paths=existing_files,
        existing_directory_paths=existing_dirs,
    )
    payload.update(_result_payload(top))

    steps_out: list[dict[str, Any]] = []
    plan_needs_revision = top.needs_revision
    for raw_step in payload.get("implementation_steps") or []:
        step = dict(raw_step)
        step_files = step.get("target_files")
        step_dirs = step.get("target_directories")
        if not step_files and not step_dirs:
            step_files = top.target_files
            step_dirs = top.target_directories
        normalized = normalize_plan_targets(
            title=str(step.get("title") or ""),
            description=str(step.get("description") or ""),
            goal=str(step.get("goal") or ""),
            action_type=step.get("action_type"),
            patch_task_kind=step.get("patch_task_kind") or (top.patch_task_kind if not step_files and not step_dirs else ""),
            target_files=step_files,
            target_directories=step_dirs,
            operations=step.get("operations"),
            assumptions=step.get("assumptions") or top.assumptions,
            existing_file_paths=existing_files,
            existing_directory_paths=existing_dirs,
        )
        step.update(_result_payload(normalized))
        plan_needs_revision = plan_needs_revision or normalized.needs_revision
        steps_out.append(step)
    payload["implementation_steps"] = steps_out
    if plan_needs_revision:
        payload["status"] = "needs_revision"
    return _model_validate(plan, payload)


def validate_plan_target_contract(value: Any) -> TargetValidationResult:
    payload = _model_dump(value) if not isinstance(value, dict) else dict(value)
    reasons: list[str] = []
    warnings: list[str] = []
    unsupported: list[str] = []
    for path in _as_str_list(payload.get("target_files")):
        cleaned = _clean_path(path)
        if not _is_safe_rel_path(cleaned):
            reasons.append(f"unsafe_target_file:{cleaned}")
    for path in _as_str_list(payload.get("target_directories")):
        cleaned = _clean_path(path)
        if not _is_safe_rel_path(cleaned):
            reasons.append(f"unsafe_target_directory:{cleaned}")
    files = {_clean_path(p) for p in _as_str_list(payload.get("target_files"))}
    dirs = {_clean_path(p) for p in _as_str_list(payload.get("target_directories"))}
    overlap = sorted((files & dirs) - {""})
    if overlap:
        reasons.append("target_kind_conflict:" + ",".join(overlap))
    ops = _operation_dicts(payload.get("operations"))
    for op in ops:
        op_type = str(op.get("type") or "")
        if op_type not in PLAN_OPERATION_TYPES:
            reasons.append(f"invalid_operation_type:{op_type}")
        if op_type in UNSUPPORTED_OPERATION_TYPES:
            unsupported.append(op_type)
            reasons.append(f"unsupported_operation:{op_type}")
        for path in [str(op.get("path") or ""), *_as_str_list(op.get("paths"))]:
            cleaned = _clean_path(path)
            if cleaned and not _is_safe_rel_path(cleaned):
                reasons.append(f"unsafe_operation_path:{cleaned}")
    kind = str(payload.get("patch_task_kind") or "")
    if kind and kind not in PATCH_TASK_KINDS:
        reasons.append(f"invalid_patch_task_kind:{kind}")
    if kind == "structural_change" and not dirs and not files:
        reasons.append("structural_targets_missing")
    if kind == "structural_change" and dirs and not _structural_materializable(dirs, ops):
        warnings.append("structural_targets_require_patch_materialization")
    for step in payload.get("implementation_steps") or []:
        step_result = validate_plan_target_contract(step)
        reasons.extend(step_result.reasons)
        warnings.extend(step_result.warnings)
        unsupported.extend(step_result.unsupported_operations)
    return TargetValidationResult(
        ok=not reasons,
        reasons=_dedup(reasons),
        warnings=_dedup(warnings),
        unsupported_operations=_dedup(unsupported),
    )


def materialize_structural_targets(value: Any) -> StructuralMaterializationResult:
    payload = _model_dump(value) if not isinstance(value, dict) else dict(value)
    files = [_clean_path(p) for p in _as_str_list(payload.get("target_files")) if _clean_path(p)]
    dirs = [_clean_path(p) for p in _as_str_list(payload.get("target_directories")) if _clean_path(p)]
    operations = _operation_dicts(payload.get("operations"))
    assumptions = _as_str_list(payload.get("assumptions"))
    diagnostics: list[dict[str, Any]] = []
    if any(str(op.get("type") or "") in UNSUPPORTED_OPERATION_TYPES for op in operations):
        return StructuralMaterializationResult(
            status="unsupported",
            normalized_target_files=files,
            normalized_target_directories=dirs,
            normalized_operations=operations,
            assumptions=assumptions,
            diagnostics=[{"reason": "unsupported_operation", "operation_type": "remove_directory"}],
        )
    validation = validate_plan_target_contract({**payload, "implementation_steps": []})
    if any(reason.startswith("unsafe_") for reason in validation.reasons):
        return StructuralMaterializationResult(
            status="blocked",
            normalized_target_files=files,
            normalized_target_directories=dirs,
            normalized_operations=operations,
            assumptions=assumptions,
            diagnostics=[{"reason": reason} for reason in validation.reasons],
        )
    if str(payload.get("patch_task_kind") or "") != "structural_change" and not dirs:
        return StructuralMaterializationResult(
            status="not_required",
            patch_target_files=files,
            normalized_target_files=files,
            normalized_target_directories=dirs,
            normalized_operations=operations,
            assumptions=assumptions,
        )
    patch_files = list(files)
    file_changes: list[dict[str, Any]] = []
    for directory in dirs:
        if any(_path_materializes_dir(path, directory) for path in patch_files):
            continue
        placeholder = f"{directory.rstrip('/')}/.gitkeep"
        patch_files.append(placeholder)
        file_changes.append(
            {
                "path": placeholder,
                "action_type": "create",
                "content_mode": "full_content",
                "proposed_content": "\n",
                "metadata": {
                    "materialized_from_directory": directory,
                    "materialization_reason": "git_cannot_track_empty_directory",
                },
            }
        )
        diagnostics.append({"reason": "directory_materialized_with_placeholder", "directory": directory, "path": placeholder})
    return StructuralMaterializationResult(
        status="materialized" if file_changes else "not_required",
        patch_target_files=_dedup(patch_files),
        file_changes=file_changes,
        normalized_target_files=files,
        normalized_target_directories=dirs,
        normalized_operations=operations,
        assumptions=_dedup([*assumptions, "Empty directory requirements are materialized only in patch-generation metadata."]),
        diagnostics=diagnostics,
        missing_evidence=[f"Tracked file materializing {directory}" for directory in dirs],
    )


def compatibility_fill_plan_pool_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Schema-only compatibility fill for old PlanPool JSON payloads."""
    out = copy.deepcopy(payload)
    for item in out.get("items") or []:
        if not isinstance(item, dict):
            continue
        item.setdefault("schema_version", PLAN_TARGET_CONTRACT_SCHEMA_VERSION)
        item.setdefault("patch_task_kind", "")
        item.setdefault("target_directories", [])
        item.setdefault("operations", [])
        item.setdefault("assumptions", [])
        item.setdefault("normalization_diagnostics", [])
    return out


def _result_payload(result: TargetNormalizationResult) -> dict[str, Any]:
    return {
        "schema_version": result.schema_version,
        "patch_task_kind": result.patch_task_kind,
        "target_files": list(result.target_files),
        "target_directories": list(result.target_directories),
        "operations": [op.model_dump() for op in result.operations],
        "assumptions": list(result.assumptions),
        "normalization_diagnostics": list(result.normalization_diagnostics),
    }


def _build_operations(*, files: list[str], directories: list[str], action_type: str) -> list[PlanOperation]:
    action = str(action_type or "").strip().lower()
    ops: list[PlanOperation] = []
    if directories:
        ops.append(PlanOperation(type="create_structure", paths=directories, reason="normalized_target_directories"))
    for path in files:
        op_type: PlanOperationType = "create_file" if action in {"create", "add", "write"} else "modify_file"
        if action == "delete":
            op_type = "delete_file"
        ops.append(PlanOperation(type=op_type, path=path, reason="normalized_target_files"))
    return ops


def _normalize_operations(value: Any) -> tuple[list[PlanOperation], list[dict[str, Any]]]:
    out: list[PlanOperation] = []
    diagnostics: list[dict[str, Any]] = []
    for raw in value or []:
        if isinstance(raw, PlanOperation):
            op = raw
        elif isinstance(raw, dict):
            op_type = str(raw.get("type") or "")
            if op_type not in PLAN_OPERATION_TYPES:
                diagnostics.append({"reason": "invalid_operation_type", "operation_type": op_type})
                continue
            op = PlanOperation(
                type=op_type,  # type: ignore[arg-type]
                path=_clean_path(raw.get("path") or ""),
                paths=[_clean_path(p) for p in _as_str_list(raw.get("paths")) if _clean_path(p)],
                reason=str(raw.get("reason") or ""),
            )
        else:
            diagnostics.append({"reason": "invalid_operation", "value": str(raw)[:80]})
            continue
        out.append(op)
    return out, diagnostics


def _operation_dicts(value: Any) -> list[dict[str, Any]]:
    ops: list[dict[str, Any]] = []
    for raw in value or []:
        if isinstance(raw, PlanOperation):
            ops.append(raw.model_dump())
        elif isinstance(raw, dict):
            ops.append(dict(raw))
    return ops


def _infer_patch_task_kind(*, files: list[str], directories: list[str], text: str) -> PatchTaskKind:
    if directories and files:
        return "mixed_change"
    if directories:
        return "structural_change"
    lowered = " ".join(files).lower() + " " + text.lower()
    if any(path.lower().startswith("tests/") or "/test_" in path.lower() or path.lower().startswith("test_") for path in files):
        return "test_change"
    if any(path.lower().endswith((".md", ".rst", ".txt")) or path.lower().startswith("docs/") for path in files):
        return "documentation_change"
    if any(PurePosixPath(path).name.lower() in CONFIG_NAMES or path.lower().endswith((".toml", ".yaml", ".yml", ".json", ".ini", ".env")) for path in files):
        return "configuration_change"
    if "test" in lowered:
        return "test_change"
    return "code_change"


def _normalize_patch_task_kind(value: Any) -> PatchTaskKind | None:
    candidate = str(value or "").strip()
    return candidate if candidate in PATCH_TASK_KINDS else None  # type: ignore[return-value]


def _should_treat_as_directory(
    path: str,
    *,
    text: str,
    child_parent_dirs: set[str],
    existing_files: set[str],
    existing_dirs: set[str],
) -> bool:
    lowered_name = PurePosixPath(path).name.lower()
    if path in existing_files or lowered_name in KNOWN_EXTENSIONLESS_FILES:
        return False
    if path in existing_dirs or path in child_parent_dirs or path.endswith("/"):
        return True
    suffix = PurePosixPath(path).suffix
    if suffix:
        return False
    return bool(DIRECTORY_INTENT_RE.search(text))


def _parents_named_by_children(paths: set[str]) -> set[str]:
    parents: set[str] = set()
    for path in paths:
        parts = PurePosixPath(path).parts
        for idx in range(1, len(parts)):
            parent = "/".join(parts[:idx])
            if parent in paths:
                parents.add(parent)
    return parents


def _structural_materializable(dirs: set[str], ops: list[dict[str, Any]]) -> bool:
    if not dirs:
        return True
    op_types = {str(op.get("type") or "") for op in ops}
    return bool(op_types & {"create_structure", "create_directory"})


def _path_materializes_dir(path: str, directory: str) -> bool:
    d = directory.rstrip("/")
    return path == d or path.startswith(f"{d}/")


def _repo_paths_from_context(text: str) -> tuple[set[str], set[str]]:
    files: set[str] = set()
    dirs: set[str] = set()
    for line in str(text or "").splitlines():
        value = line.strip().lstrip("-").strip()
        if not value:
            continue
        candidate = _clean_path(value.split()[0])
        if not candidate or not _is_safe_rel_path(candidate):
            continue
        if PurePosixPath(candidate).suffix or PurePosixPath(candidate).name.lower() in KNOWN_EXTENSIONLESS_FILES:
            files.add(candidate)
            for idx in range(1, len(PurePosixPath(candidate).parts)):
                dirs.add("/".join(PurePosixPath(candidate).parts[:idx]))
    return files, dirs


def _clean_path(value: Any) -> str:
    return str(value or "").strip().replace("\\", "/").strip("/")


def _is_safe_rel_path(path: str) -> bool:
    if not path or "\x00" in path:
        return False
    if re.match(r"^[A-Za-z]:/", path):
        return False
    posix = PurePosixPath(path)
    return not posix.is_absolute() and ".." not in posix.parts


def _as_str_list(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list | tuple | set):
        return [str(v).strip() for v in value if str(v).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _dedup(values: list[str]) -> list[str]:
    return list(dict.fromkeys([str(v).strip() for v in values if str(v).strip()]))


def _diag(reason: str, path: str, source: str) -> dict[str, Any]:
    return {"reason": reason, "path": path, "source": source}


def _model_dump(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return copy.deepcopy(value)
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    return {}


def _model_validate(original: Any, payload: dict[str, Any]) -> Any:
    model_type = original.__class__
    if hasattr(model_type, "model_validate"):
        return model_type.model_validate(payload)
    return model_type(**payload)
