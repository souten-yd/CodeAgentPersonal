from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AtlasConversationStore:
    """Per-project (per-workspace) persistence for the Atlas conversational shell.

    The Atlas Claude shell transcript used to live only in browser memory, so a
    reload wiped all chat / plan / run history. This store persists the
    transcript server-side under the resolved ca_data root so the browser can be
    a thin client: on load it re-fetches everything for the active project.

    Layout: ``<root>/atlas/workspaces/<workspace_id>/conversation/``
      - ``messages.ndjson`` : append-only transcript (one JSON object per line)
      - ``meta.json``       : ``{active_pool_id, latest_autopilot_run_id, provisional}``
    """

    ALLOWED_ROLES = {"user", "atlas", "system"}

    def __init__(self, root_dir: Path | str, workspace_id: str = "default"):
        self.root_dir = Path(root_dir)
        self.workspace_id = self._validate_storage_id(workspace_id, "workspace_id")

    # ── paths ──
    def conversation_dir(self) -> Path:
        return self.root_dir / "atlas" / "workspaces" / self.workspace_id / "conversation"

    def messages_path(self) -> Path:
        return self.conversation_dir() / "messages.ndjson"

    def meta_path(self) -> Path:
        return self.conversation_dir() / "meta.json"

    # ── transcript ──
    def append(self, role: str, text: str, ts: int | None = None, meta: dict[str, Any] | None = None) -> dict[str, Any]:
        safe_role = role if role in self.ALLOWED_ROLES else "system"
        record = {
            "role": safe_role,
            "text": str(text),
            "ts": int(ts) if ts is not None else int(datetime.now(timezone.utc).timestamp() * 1000),
            "created_at": _utc_now_iso(),
        }
        path = self.messages_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        # Optional meta side-channel: keep active pool / run pointers fresh so a
        # reload can re-render the latest plan and autopilot summary.
        if meta:
            updates = {k: meta[k] for k in ("active_pool_id", "latest_autopilot_run_id") if meta.get(k)}
            if updates:
                self.write_meta(updates)
        return record

    def list(self, limit: int | None = None) -> list[dict[str, Any]]:
        path = self.messages_path()
        if not path.exists():
            return []
        messages: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                messages.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        if limit is not None and limit > 0:
            return messages[-limit:]
        return messages

    def clear(self) -> None:
        path = self.messages_path()
        if path.exists():
            path.unlink()

    # ── meta ──
    def read_meta(self) -> dict[str, Any]:
        path = self.meta_path()
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def write_meta(self, updates: dict[str, Any]) -> dict[str, Any]:
        meta = self.read_meta()
        meta.update(updates)
        path = self.meta_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        return meta

    @staticmethod
    def _validate_storage_id(value: str, field_name: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError(f"invalid {field_name}: empty value is not allowed")
        if "/" in text or "\\" in text or ".." in text:
            raise ValueError(f"invalid {field_name}: path traversal tokens are not allowed")
        return text
