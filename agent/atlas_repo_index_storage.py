from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

_HASH_RE = re.compile(r"^[0-9a-f]{8,64}$")


class AtlasRepoIndexStorage:
    def __init__(self, data_root: Path):
        self.base = Path(data_root) / "atlas" / "repo_index"

    def project_hash(self, project_path: str) -> str:
        return hashlib.sha256(project_path.encode("utf-8")).hexdigest()[:16]

    def _validate_project_hash(self, project_hash: str) -> str:
        if not _HASH_RE.fullmatch(project_hash or ""):
            raise ValueError("invalid project_hash")
        return project_hash

    def dir_for(self, project_path: str) -> Path:
        d = self.base / self.project_hash(project_path)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def dir_for_hash(self, project_hash: str) -> Path:
        d = self.base / self._validate_project_hash(project_hash)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def save_json(self, project_path: str, name: str, payload: dict):
        p = self.dir_for(project_path) / name
        p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(p)

    def load_json(self, project_path: str, name: str) -> dict:
        p = self.dir_for(project_path) / name
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

    def load_result_by_hash(self, project_hash: str, index_run_id: str) -> dict:
        if not index_run_id.startswith("repoindex_"):
            raise ValueError("invalid index_run_id")
        p = self.dir_for_hash(project_hash) / f"{index_run_id}.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
