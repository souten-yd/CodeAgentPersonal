"""Portal x Forge trace sidecar (PFG-27).

Reads and writes an optional Forge provenance sidecar for a Portal installation. The
sidecar lives next to the installation (``installation_root/forge_trace.json``), never
inside the immutable package archive and never in exported runtime data, so it is safe by
construction and absent for legacy runs.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.portal.contracts import PortalForgeTrace
from app.portal.paths import PortalPathLayout


def _trace_path(layout: PortalPathLayout, installation_id: str) -> Path:
    return layout.installation_root(installation_id) / "forge_trace.json"


def write_forge_trace(data_root: str | Path, trace: PortalForgeTrace) -> PortalForgeTrace:
    layout = PortalPathLayout(Path(data_root))
    if not trace.recorded_at:
        trace = trace.model_copy(update={"recorded_at": datetime.now(timezone.utc).isoformat()})
    path = _trace_path(layout, trace.installation_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(trace.model_dump(mode="json"), ensure_ascii=False, indent=2),
                    encoding="utf-8")
    return trace


def read_forge_trace(data_root: str | Path, installation_id: str) -> PortalForgeTrace | None:
    layout = PortalPathLayout(Path(data_root))
    path = _trace_path(layout, installation_id)
    if not path.exists():
        return None
    return PortalForgeTrace.model_validate_json(path.read_text(encoding="utf-8"))


__all__ = ["write_forge_trace", "read_forge_trace"]
