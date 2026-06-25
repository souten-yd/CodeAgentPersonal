from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any


EDIT_PRIMITIVE_OPS = {
    "replace_exact",
    "search_replace",
    "replace_symbol",
    "insert_import",
    "replace_object_property",
    "replace_json_pointer",
    "replace_yaml_path",
    "replace_sql_statement",
    "replace_route_handler",
    "replace_component_prop",
}

IMPLEMENTED_EDIT_PRIMITIVE_OPS = {
    "replace_exact",
    "search_replace",
    "insert_import",
    "replace_json_pointer",
}


@dataclass(frozen=True)
class EditPrimitivePolicy:
    file_path: str
    edit_only: bool
    preferred_primitives: tuple[str, ...]
    forbidden_modes: tuple[str, ...]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "edit_only": self.edit_only,
            "preferred_primitives": list(self.preferred_primitives),
            "forbidden_modes": list(self.forbidden_modes),
            "reason": self.reason,
        }


def file_type_edit_policy(file_path: str, *, file_lines: int = 0, file_chars: int = 0) -> EditPrimitivePolicy:
    path = str(file_path or "").strip().replace("\\", "/")
    suffixes = tuple(PurePosixPath(path).suffixes)
    suffix = suffixes[-1].lower() if suffixes else ""
    name = PurePosixPath(path).name.lower()
    lowered = path.lower()

    if name.startswith(".env"):
        return EditPrimitivePolicy(path, True, ("replace_object_property",), ("full_content",), "env_key_only")
    if lowered.endswith("openapi.yaml") or lowered.endswith("openapi.yml") or lowered.endswith("swagger.json"):
        return EditPrimitivePolicy(path, True, ("replace_yaml_path", "replace_json_pointer"), ("full_content",), "schema_path_required")
    if suffix in {".json"}:
        return EditPrimitivePolicy(path, True, ("replace_json_pointer",), ("full_content",), "json_pointer_required")
    if suffix in {".yaml", ".yml"}:
        return EditPrimitivePolicy(path, True, ("replace_yaml_path",), ("full_content",), "yaml_path_required")
    if suffix in {".sql"} or "migrations/" in lowered or lowered.endswith("schema.prisma"):
        return EditPrimitivePolicy(path, True, ("replace_sql_statement", "replace_exact"), ("full_content",), "schema_edit_only")
    if suffix in {".ts", ".tsx", ".js", ".jsx", ".vue", ".svelte"}:
        edit_only = file_lines >= 80 or file_chars >= 8000
        return EditPrimitivePolicy(
            path,
            edit_only,
            ("replace_symbol", "replace_component_prop", "replace_route_handler", "insert_import", "replace_exact"),
            ("full_content",) if edit_only else (),
            "web_code_prefer_symbol_or_component",
        )
    if suffix == ".py":
        edit_only = file_lines >= 160 or file_chars >= 12000 or any(part in lowered for part in ("/service", "/domain"))
        return EditPrimitivePolicy(
            path,
            edit_only,
            ("replace_symbol", "insert_import", "replace_exact"),
            ("full_content",) if edit_only else (),
            "python_prefer_symbol_edit",
        )
    return EditPrimitivePolicy(path, False, ("replace_exact", "search_replace"), (), "default_exact_edit")


def apply_edit_primitives(text: str, primitives: list[Any], *, file_path: str = "") -> dict[str, Any]:
    if not isinstance(primitives, list) or not primitives:
        return {"status": "blocked", "reason": "edit_primitives_missing"}
    result = text
    applied_ops: list[str] = []
    for raw in primitives:
        if not isinstance(raw, dict):
            return {"status": "blocked", "reason": "invalid_edit_primitive"}
        op = str(raw.get("op") or raw.get("type") or "").strip()
        if op not in EDIT_PRIMITIVE_OPS:
            return {"status": "blocked", "reason": "unknown_edit_primitive"}
        if op not in IMPLEMENTED_EDIT_PRIMITIVE_OPS:
            return {"status": "blocked", "reason": "unsupported_edit_primitive"}
        if op in {"replace_exact", "search_replace"}:
            applied = _apply_replace_exact(result, raw)
        elif op == "replace_json_pointer":
            applied = _apply_replace_json_pointer(result, raw)
        elif op == "insert_import":
            applied = _apply_insert_import(result, raw, file_path=file_path)
        else:
            applied = {"status": "blocked", "reason": "unsupported_edit_primitive"}
        if applied.get("status") != "ok":
            return applied
        result = str(applied.get("content") or "")
        applied_ops.append(op)
    return {"status": "ok", "content": result, "mode": "edit_primitives", "applied_ops": applied_ops}


def _apply_replace_exact(text: str, primitive: dict[str, Any]) -> dict[str, Any]:
    old = str(primitive.get("old_string") if primitive.get("old_string") is not None else primitive.get("search") or "")
    new = str(primitive.get("new_string") if primitive.get("new_string") is not None else primitive.get("replace") or "")
    if not old:
        return {"status": "blocked", "reason": "edit_primitive_not_applicable"}
    if text.count(old) != 1:
        return {"status": "blocked", "reason": "edit_primitive_not_applicable"}
    return {"status": "ok", "content": text.replace(old, new, 1)}


def _apply_replace_json_pointer(text: str, primitive: dict[str, Any]) -> dict[str, Any]:
    pointer = str(primitive.get("path") or primitive.get("json_pointer") or "").strip()
    if not pointer.startswith("/"):
        return {"status": "blocked", "reason": "edit_primitive_not_applicable"}
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {"status": "blocked", "reason": "edit_primitive_not_applicable"}
    tokens = [_unescape_json_pointer(part) for part in pointer.split("/")[1:]]
    if not tokens:
        return {"status": "blocked", "reason": "edit_primitive_not_applicable"}
    target: Any = data
    for token in tokens[:-1]:
        if isinstance(target, dict) and token in target:
            target = target[token]
        elif isinstance(target, list) and token.isdigit() and int(token) < len(target):
            target = target[int(token)]
        else:
            return {"status": "blocked", "reason": "edit_primitive_not_applicable"}
    last = tokens[-1]
    value = primitive.get("value")
    if isinstance(target, dict) and last in target:
        target[last] = value
    elif isinstance(target, list) and last.isdigit() and int(last) < len(target):
        target[int(last)] = value
    else:
        return {"status": "blocked", "reason": "edit_primitive_not_applicable"}
    trailing = "\n" if text.endswith("\n") else ""
    return {"status": "ok", "content": json.dumps(data, indent=2, ensure_ascii=False) + trailing}


def _unescape_json_pointer(token: str) -> str:
    return token.replace("~1", "/").replace("~0", "~")


def _apply_insert_import(text: str, primitive: dict[str, Any], *, file_path: str) -> dict[str, Any]:
    statement = _import_statement(primitive, file_path=file_path)
    if not statement:
        return {"status": "blocked", "reason": "edit_primitive_not_applicable"}
    statement = statement.rstrip()
    if not statement:
        return {"status": "blocked", "reason": "edit_primitive_not_applicable"}
    if statement in text.splitlines():
        return {"status": "ok", "content": text}
    suffix = PurePosixPath(str(file_path or "")).suffix.lower()
    if suffix == ".py":
        if not (statement.startswith("import ") or statement.startswith("from ")):
            return {"status": "blocked", "reason": "edit_primitive_not_applicable"}
        return {"status": "ok", "content": _insert_python_import(text, statement)}
    if suffix in {".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte"}:
        if not statement.startswith("import "):
            return {"status": "blocked", "reason": "edit_primitive_not_applicable"}
        return {"status": "ok", "content": _insert_js_import(text, statement)}
    return {"status": "blocked", "reason": "edit_primitive_not_applicable"}


def _import_statement(primitive: dict[str, Any], *, file_path: str) -> str:
    explicit = primitive.get("import_statement") or primitive.get("statement") or primitive.get("import")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    module = str(primitive.get("module") or "").strip()
    name = str(primitive.get("name") or primitive.get("symbol") or "").strip()
    suffix = PurePosixPath(str(file_path or "")).suffix.lower()
    if suffix == ".py" and module and name:
        return f"from {module} import {name}"
    return ""


def _insert_python_import(text: str, statement: str) -> str:
    lines = text.splitlines(keepends=True)
    if not lines:
        return statement + "\n"
    insert_at = 0
    while insert_at < len(lines) and (
        lines[insert_at].startswith("#!")
        or "coding" in lines[insert_at].lower()
        or lines[insert_at].strip() == ""
    ):
        insert_at += 1
    while insert_at < len(lines) and (lines[insert_at].startswith("import ") or lines[insert_at].startswith("from ")):
        insert_at += 1
    return "".join(lines[:insert_at] + [statement + "\n"] + lines[insert_at:])


def _insert_js_import(text: str, statement: str) -> str:
    lines = text.splitlines(keepends=True)
    insert_at = 0
    while insert_at < len(lines) and (lines[insert_at].startswith("//") or lines[insert_at].strip() == ""):
        insert_at += 1
    while insert_at < len(lines) and lines[insert_at].lstrip().startswith("import "):
        insert_at += 1
    return "".join(lines[:insert_at] + [statement + "\n"] + lines[insert_at:])
