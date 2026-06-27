from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


PROJECT_METADATA_FILENAME = "project.json"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def project_metadata_path(root_dir: Path | str, project_name: str) -> Path:
    return Path(root_dir) / "atlas" / "projects" / str(project_name or "") / PROJECT_METADATA_FILENAME


def read_project_metadata(root_dir: Path | str, project_name: str) -> dict[str, Any]:
    path = project_metadata_path(root_dir, project_name)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def new_project_instance_id() -> str:
    return f"projinst_{uuid4().hex}"


def ensure_project_metadata(
    root_dir: Path | str,
    project_name: str,
    *,
    display_name: str = "",
    provisional: bool | None = None,
) -> dict[str, Any]:
    name = str(project_name or "").strip()
    path = project_metadata_path(root_dir, name)
    payload = read_project_metadata(root_dir, name)
    now = utc_now_iso()
    changed = False
    if not payload.get("project_instance_id"):
        payload["project_instance_id"] = new_project_instance_id()
        changed = True
    if not payload.get("created_at"):
        payload["created_at"] = now
        changed = True
    if payload.get("name") != name:
        payload["name"] = name
        changed = True
    if display_name and payload.get("display_name") != display_name:
        payload["display_name"] = display_name
        changed = True
    elif not payload.get("display_name"):
        payload["display_name"] = name
        changed = True
    if provisional is not None and bool(payload.get("provisional", False)) != bool(provisional):
        payload["provisional"] = bool(provisional)
        changed = True
    if changed or not path.exists():
        payload["updated_at"] = now
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def project_instance_id_from_metadata(metadata: dict[str, Any] | None) -> str:
    if not isinstance(metadata, dict):
        return ""
    for key in ("project_instance_id", "projectInstanceId", "runtime_project_instance_id"):
        value = str(metadata.get(key) or "").strip()
        if value:
            return value
    runtime_scope = metadata.get("runtime_scope") if isinstance(metadata.get("runtime_scope"), dict) else {}
    value = str(runtime_scope.get("project_instance_id") or runtime_scope.get("projectInstanceId") or "").strip()
    if value:
        return value
    owner = metadata.get("plan_pool_owner") if isinstance(metadata.get("plan_pool_owner"), dict) else {}
    return str(owner.get("project_instance_id") or owner.get("projectInstanceId") or "").strip()
