from __future__ import annotations

from pathlib import Path


def resolve_atlas_workspace_root(*, ca_data_root: Path, workspace_id: str, project_path: str = "", mode: str = "project_or_workspace") -> Path:
    _ = mode
    candidate = str(project_path or "").strip()
    if candidate:
        return Path(candidate).expanduser().resolve()
    return (Path(ca_data_root).expanduser().resolve() / "atlas" / "workspaces" / str(workspace_id or "default")).resolve()
