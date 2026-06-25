from __future__ import annotations

import json
import re
from pathlib import PurePosixPath
from typing import Any

from agent.atlas_contract_registry import evaluate_project_contracts
from agent.atlas_contracts import violation


_IMPORT_NAMED_RE = re.compile(r"import\s+\{(?P<names>[^}]+)\}\s+from\s+['\"](?P<source>\.[^'\"]+)['\"]")
_EXPORT_RE = re.compile(
    r"\bexport\s+(?:async\s+)?(?:function|class|const|let|var)\s+(?P<name>[A-Za-z_$][\w$]*)|"
    r"\bexport\s*\{\s*(?P<named>[^}]+)\}",
    re.MULTILINE,
)
_SLICE_MARKERS = (
    "unrelated line(s) omitted",
    "full file is on disk",
    "rest of the file unchanged",
    "rest unchanged",
    "... omitted",
)


def run_post_apply_validators(
    post_apply_content_by_path: dict[str, str],
    *,
    preview_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    content_by_path = _normalize_content_map(post_apply_content_by_path)
    checks = [
        import_export_validator(content_by_path),
        json_shape_validator(content_by_path),
        config_env_key_validator(content_by_path),
        api_route_reference_validator(content_by_path),
        resource_contract_validator(content_by_path),
        forbidden_full_content_validator(content_by_path, preview_result=preview_result),
        slice_marker_validator(content_by_path),
    ]
    violations: list[dict[str, Any]] = []
    warnings: list[str] = []
    validators: list[dict[str, Any]] = []
    for check in checks:
        check_violations = list(check.get("violations") or [])
        check_warnings = [str(w) for w in (check.get("warnings") or []) if str(w)]
        validators.append({
            "name": str(check.get("name") or "unknown"),
            "status": "failed" if check_violations else "passed",
            "violation_count": len(check_violations),
        })
        violations.extend(check_violations)
        warnings.extend(check_warnings)
    return {
        "violations": violations,
        "warnings": list(dict.fromkeys(warnings)),
        "validators": validators,
    }


def import_export_validator(post_apply_content_by_path: dict[str, str]) -> dict[str, Any]:
    content_by_path = _normalize_content_map(post_apply_content_by_path)
    exports_by_path = {path: _exported_names(content) for path, content in content_by_path.items()}
    violations: list[dict[str, Any]] = []
    for path, content in content_by_path.items():
        if PurePosixPath(path).suffix.lower() not in {".js", ".jsx", ".ts", ".tsx", ".mjs"}:
            continue
        for match in _IMPORT_NAMED_RE.finditer(content):
            source = match.group("source")
            target_path = _resolve_relative_import(path, source, content_by_path)
            if not target_path:
                violations.append(violation(
                    code="import_target_missing",
                    contract_type="interface",
                    path=path,
                    evidence={"source": source},
                ))
                continue
            imported = _imported_names(match.group("names"))
            exported = exports_by_path.get(target_path, set())
            missing = sorted(name for name in imported if name not in exported)
            for name in missing:
                violations.append(violation(
                    code="import_export_missing_export",
                    contract_type="interface",
                    path=path,
                    evidence={"source": source, "resolved_path": target_path, "imported_name": name, "exported_names": sorted(exported)},
                ))
    return {"name": "import_export_validator", "violations": violations, "warnings": []}


def json_shape_validator(post_apply_content_by_path: dict[str, str]) -> dict[str, Any]:
    content_by_path = _normalize_content_map(post_apply_content_by_path)
    violations: list[dict[str, Any]] = []
    for path, content in content_by_path.items():
        if PurePosixPath(path).suffix.lower() != ".json":
            continue
        try:
            json.loads(content)
        except json.JSONDecodeError as exc:
            violations.append(violation(
                code="json_invalid",
                contract_type="data",
                path=path,
                evidence={"line": exc.lineno, "column": exc.colno, "message": exc.msg},
            ))
    violations.extend(_filter_contract_violations(content_by_path, {"form_validation_field_mismatch"}))
    return {"name": "json_shape_validator", "violations": violations, "warnings": []}


def config_env_key_validator(post_apply_content_by_path: dict[str, str]) -> dict[str, Any]:
    content_by_path = _normalize_content_map(post_apply_content_by_path)
    return {
        "name": "config_env_key_validator",
        "violations": _filter_contract_violations(content_by_path, {"env_key_mismatch"}),
        "warnings": [],
    }


def api_route_reference_validator(post_apply_content_by_path: dict[str, str]) -> dict[str, Any]:
    content_by_path = _normalize_content_map(post_apply_content_by_path)
    return {
        "name": "api_route_reference_validator",
        "violations": _filter_contract_violations(content_by_path, {"api_route_missing_handler"}),
        "warnings": [],
    }


def resource_contract_validator(post_apply_content_by_path: dict[str, str]) -> dict[str, Any]:
    content_by_path = _normalize_content_map(post_apply_content_by_path)
    return {
        "name": "resource_contract_validator",
        "violations": _filter_contract_violations(content_by_path, {"webgl_canvas_2d_context_conflict"}),
        "warnings": [],
    }


def forbidden_full_content_validator(
    post_apply_content_by_path: dict[str, str],
    *,
    preview_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _ = post_apply_content_by_path
    violations: list[dict[str, Any]] = []
    for result in _preview_file_results(preview_result):
        mode = str(result.get("content_mode") or result.get("mode") or "").strip()
        if mode != "full_content":
            continue
        if bool(result.get("target_existed")) and not bool(result.get("full_content_allowed")):
            violations.append(violation(
                code="forbidden_full_content",
                contract_type="resource",
                path=str(result.get("path") or ""),
                evidence={"content_mode": mode, "target_existed": True},
            ))
    return {"name": "forbidden_full_content_validator", "violations": violations, "warnings": []}


def slice_marker_validator(post_apply_content_by_path: dict[str, str]) -> dict[str, Any]:
    content_by_path = _normalize_content_map(post_apply_content_by_path)
    violations: list[dict[str, Any]] = []
    for path, content in content_by_path.items():
        lowered = content.lower()
        marker = next((candidate for candidate in _SLICE_MARKERS if candidate in lowered), "")
        if marker:
            violations.append(violation(
                code="slice_marker_present",
                contract_type="resource",
                path=path,
                evidence={"marker": marker},
            ))
    return {"name": "slice_marker_validator", "violations": violations, "warnings": []}


def _filter_contract_violations(content_by_path: dict[str, str], codes: set[str]) -> list[dict[str, Any]]:
    result = evaluate_project_contracts(content_by_path)
    return [dict(item) for item in result.get("violations") or [] if str(item.get("code") or "") in codes]


def _normalize_content_map(post_apply_content_by_path: dict[str, str]) -> dict[str, str]:
    return {
        str(path).replace("\\", "/"): str(content or "")
        for path, content in (post_apply_content_by_path or {}).items()
        if str(path).strip()
    }


def _exported_names(content: str) -> set[str]:
    names: set[str] = set()
    for match in _EXPORT_RE.finditer(content):
        name = match.group("name")
        if name:
            names.add(name)
        named = match.group("named")
        if named:
            names.update(_imported_names(named))
    return names


def _imported_names(raw_names: str) -> set[str]:
    names: set[str] = set()
    for raw in str(raw_names or "").split(","):
        value = raw.strip()
        if not value:
            continue
        left = re.split(r"\s+as\s+", value, maxsplit=1)[0].strip()
        if left:
            names.add(left)
    return names


def _resolve_relative_import(importer_path: str, source: str, content_by_path: dict[str, str]) -> str:
    base_parts = PurePosixPath(importer_path).parent.parts
    candidate = PurePosixPath(*base_parts, source).as_posix()
    candidate = _normalize_posix_path(candidate)
    suffixes = ("", ".ts", ".tsx", ".js", ".jsx", ".mjs", "/index.ts", "/index.tsx", "/index.js", "/index.jsx")
    for suffix in suffixes:
        path = candidate + suffix
        if path in content_by_path:
            return path
    return ""


def _normalize_posix_path(path: str) -> str:
    parts: list[str] = []
    for part in PurePosixPath(path).parts:
        if part in {"", "."}:
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return "/".join(parts)


def _preview_file_results(preview_result: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(preview_result, dict):
        return []
    raw = preview_result.get("file_results")
    if not isinstance(raw, list):
        raw = [*list(preview_result.get("applied_changes") or []), *list(preview_result.get("blocked_changes") or [])]
    return [dict(item) for item in raw if isinstance(item, dict)]
