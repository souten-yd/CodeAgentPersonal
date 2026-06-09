from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath


_SAFE_ID_RE = re.compile(r"^[\w.-]+$", re.UNICODE)


def _safe_component(value: str, label: str) -> str:
    text = str(value or "").strip()
    win = PureWindowsPath(text)
    if (
        not text
        or text in {".", ".."}
        or "/" in text
        or "\\" in text
        or win.drive
        or win.root
        or not _SAFE_ID_RE.match(text)
    ):
        raise ValueError(f"invalid_{label}")
    return text


def _resolve_under(base: Path, *parts: str) -> Path:
    root = Path(base).expanduser().resolve()
    target = root.joinpath(*parts).resolve(strict=False)
    if target != root and root not in target.parents:
        raise ValueError("path_layout_escape")
    return target


@dataclass(frozen=True)
class AtlasPlayPathLayout:
    data_root: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "data_root", Path(self.data_root).expanduser().resolve())

    def atlas_project_work_root(self, project_id: str) -> Path:
        project = _safe_component(project_id, "project_id")
        return _resolve_under(self.data_root, "atlas", "projects", project, "work")

    def play_session_root(self, session_id: str) -> Path:
        session = _safe_component(session_id, "session_id")
        return _resolve_under(self.data_root, "atlas", "play", "sessions", session)

    def play_recovery_root(self, session_id: str) -> Path:
        session = _safe_component(session_id, "session_id")
        return _resolve_under(self.data_root, "atlas", "play", "recovery", session)

    def play_temp_root(self, session_id: str) -> Path:
        session = _safe_component(session_id, "session_id")
        return _resolve_under(self.data_root, "atlas", "play", "temp", session)

    def play_target_graph_root(self, project_id: str) -> Path:
        project = _safe_component(project_id, "project_id")
        return _resolve_under(self.data_root, "atlas", "play", "target_graphs", project)
