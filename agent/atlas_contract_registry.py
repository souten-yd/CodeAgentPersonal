from __future__ import annotations

import json
import re
from pathlib import PurePosixPath
from typing import Any

from agent.atlas_contracts import violation
from agent.atlas_interface_contract import build_shared_resource_contract, webgl_canvas_2d_conflict


_API_PATH_RE = re.compile(r"['\"](/api/[A-Za-z0-9_./{}:-]+)['\"]")
_FETCH_RE = re.compile(r"\b(?:fetch|axios\.(?:get|post|put|patch|delete))\(\s*['\"](/api/[A-Za-z0-9_./{}:-]+)['\"]")
_ROUTE_RE = re.compile(
    r"(?:@(?:app|router)\.(?:get|post|put|patch|delete)\(\s*['\"](?P<py>/api/[A-Za-z0-9_./{}:-]+)['\"]|"
    r"\b(?:app|router)\.(?:get|post|put|patch|delete)\(\s*['\"](?P<js>/api/[A-Za-z0-9_./{}:-]+)['\"])",
    re.MULTILINE,
)
_ENV_REF_PATTERNS = (
    re.compile(r"\bprocess\.env\.([A-Z][A-Z0-9_]*)"),
    re.compile(r"\bimport\.meta\.env\.([A-Z][A-Z0-9_]*)"),
    re.compile(r"\bos\.environ\[\s*['\"]([A-Z][A-Z0-9_]*)['\"]\s*\]"),
    re.compile(r"\bos\.getenv\(\s*['\"]([A-Z][A-Z0-9_]*)['\"]"),
)
_ENV_DEF_RE = re.compile(r"^\s*([A-Z][A-Z0-9_]*)\s*=", re.MULTILINE)


def evaluate_project_contracts(post_apply_content_by_path: dict[str, str]) -> dict[str, Any]:
    content_by_path = {
        str(path).replace("\\", "/"): str(content or "")
        for path, content in (post_apply_content_by_path or {}).items()
        if str(path).strip()
    }
    violations: list[dict[str, Any]] = []
    warnings: list[str] = []
    contracts: list[dict[str, Any]] = []

    resource_contract = build_shared_resource_contract(content_by_path)
    if resource_contract:
        contracts.append({
            "contract_type": "resource",
            "contract_id": "resource:shared_app_surface",
            "evidence": resource_contract,
        })
        violations.extend(_resource_violations(content_by_path, resource_contract))

    route_defs = _api_route_definitions(content_by_path)
    route_refs = _api_route_references(content_by_path)
    if route_defs or route_refs:
        contracts.append({
            "contract_type": "interface",
            "contract_id": "interface:api_routes",
            "evidence": {"defined": sorted(route_defs), "referenced": sorted(route_refs)},
        })
    for route, ref_paths in sorted(route_refs.items()):
        if route not in route_defs:
            for path in ref_paths:
                violations.append(violation(
                    code="api_route_missing_handler",
                    contract_type="interface",
                    path=path,
                    evidence={"route": route, "defined_routes": sorted(route_defs)},
                ))

    env_defs = _env_definitions(content_by_path)
    env_refs = _env_references(content_by_path)
    if env_defs or env_refs:
        contracts.append({
            "contract_type": "resource",
            "contract_id": "resource:env_keys",
            "evidence": {"defined": sorted(env_defs), "referenced": sorted(env_refs)},
        })
    for key, ref_paths in sorted(env_refs.items()):
        if env_defs and key not in env_defs:
            for path in ref_paths:
                violations.append(violation(
                    code="env_key_mismatch",
                    contract_type="resource",
                    path=path,
                    evidence={"key": key, "defined_keys": sorted(env_defs)},
                ))

    schema_violations, data_contracts = _schema_form_violations(content_by_path)
    violations.extend(schema_violations)
    contracts.extend(data_contracts)

    return {
        "violations": violations,
        "warnings": warnings,
        "contracts": contracts,
    }


def _resource_violations(content_by_path: dict[str, str], resource_contract: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for path, content in content_by_path.items():
        reason = webgl_canvas_2d_conflict(resource_contract, content)
        if reason:
            out.append(violation(
                code="webgl_canvas_2d_context_conflict",
                contract_type="resource",
                path=path,
                evidence={"reason": reason, "primary_canvas": resource_contract.get("primary_canvas", "")},
            ))
    return out


def _api_route_definitions(content_by_path: dict[str, str]) -> set[str]:
    routes: set[str] = set()
    for content in content_by_path.values():
        for match in _ROUTE_RE.finditer(content):
            route = match.group("py") or match.group("js") or ""
            if route:
                routes.add(_normalize_api_path(route))
    return routes


def _api_route_references(content_by_path: dict[str, str]) -> dict[str, list[str]]:
    refs: dict[str, list[str]] = {}
    for path, content in content_by_path.items():
        matches = _FETCH_RE.findall(content)
        if not matches:
            matches = _API_PATH_RE.findall(content) if not _looks_like_route_file(path) else []
        for route in matches:
            refs.setdefault(_normalize_api_path(route), []).append(path)
    return {route: sorted(set(paths)) for route, paths in refs.items()}


def _normalize_api_path(path: str) -> str:
    value = str(path or "").strip()
    value = re.sub(r"\{[^}/]+\}", "{}", value)
    value = re.sub(r":[A-Za-z_]\w*", "{}", value)
    return value.rstrip("/") or value


def _looks_like_route_file(path: str) -> bool:
    lowered = str(path).lower()
    return any(token in lowered for token in ("/api/", "routes", "router", "server", "app.py", "main.py"))


def _env_definitions(content_by_path: dict[str, str]) -> set[str]:
    keys: set[str] = set()
    for path, content in content_by_path.items():
        name = PurePosixPath(path).name.lower()
        if name.startswith(".env") or name in {"env.example", "config.env"}:
            keys.update(_ENV_DEF_RE.findall(content))
    return keys


def _env_references(content_by_path: dict[str, str]) -> dict[str, list[str]]:
    refs: dict[str, list[str]] = {}
    for path, content in content_by_path.items():
        if PurePosixPath(path).name.lower().startswith(".env"):
            continue
        for pattern in _ENV_REF_PATTERNS:
            for key in pattern.findall(content):
                refs.setdefault(key, []).append(path)
    return {key: sorted(set(paths)) for key, paths in refs.items()}


def _schema_form_violations(content_by_path: dict[str, str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    schema_fields: dict[str, set[str]] = {}
    form_fields: dict[str, set[str]] = {}
    contracts: list[dict[str, Any]] = []
    for path, content in content_by_path.items():
        suffix = PurePosixPath(path).suffix.lower()
        if suffix == ".json":
            fields = _json_schema_fields(content)
            if fields:
                schema_fields[path] = fields
        elif suffix in {".yaml", ".yml"}:
            fields = _yaml_form_fields(content)
            if fields:
                form_fields[path] = fields

    if schema_fields:
        contracts.append({
            "contract_type": "data",
            "contract_id": "data:json_schema_fields",
            "evidence": {path: sorted(fields) for path, fields in schema_fields.items()},
        })
    if form_fields:
        contracts.append({
            "contract_type": "data",
            "contract_id": "data:yaml_form_fields",
            "evidence": {path: sorted(fields) for path, fields in form_fields.items()},
        })

    violations: list[dict[str, Any]] = []
    all_form_fields = set().union(*form_fields.values()) if form_fields else set()
    if schema_fields and form_fields:
        for schema_path, fields in schema_fields.items():
            missing = sorted(fields - all_form_fields)
            for field in missing:
                violations.append(violation(
                    code="form_validation_field_mismatch",
                    contract_type="data",
                    path=schema_path,
                    evidence={"field": field, "form_fields": sorted(all_form_fields)},
                ))
    return violations, contracts


def _json_schema_fields(content: str) -> set[str]:
    try:
        data = json.loads(content)
    except Exception:
        return set()
    if not isinstance(data, dict):
        return set()
    fields: set[str] = set()
    properties = data.get("properties")
    if isinstance(properties, dict):
        fields.update(str(key) for key in properties if str(key).strip())
    required = data.get("required")
    if isinstance(required, list):
        fields.update(str(key) for key in required if str(key).strip())
    return fields


def _yaml_form_fields(content: str) -> set[str]:
    fields: set[str] = set()
    in_fields = False
    base_indent = 0
    for raw in str(content or "").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        stripped = raw.strip()
        if stripped == "fields:":
            in_fields = True
            base_indent = indent
            continue
        if in_fields and indent <= base_indent:
            in_fields = False
        if in_fields:
            match = re.match(r"([A-Za-z_][\w-]*)\s*:", stripped)
            if match:
                fields.add(match.group(1))
    return fields

