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
class PortalPathLayout:
    data_root: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "data_root", Path(self.data_root).expanduser().resolve())

    def package_store_root(self) -> Path:
        return _resolve_under(self.data_root, "portal", "packages")

    def quarantine_root(self, import_id: str) -> Path:
        return _resolve_under(self.data_root, "portal", "quarantine", _safe_component(import_id, "import_id"))

    def installation_root(self, installation_id: str) -> Path:
        return _resolve_under(
            self.data_root,
            "portal",
            "installations",
            _safe_component(installation_id, "installation_id"),
        )

    def session_application_root(self, session_id: str) -> Path:
        return _resolve_under(self.data_root, "portal", "sessions", _safe_component(session_id, "session_id"), "application")

    def session_data_root(self, session_id: str) -> Path:
        return _resolve_under(self.data_root, "portal", "sessions", _safe_component(session_id, "session_id"), "data")

    def session_cache_root(self, session_id: str) -> Path:
        return _resolve_under(self.data_root, "portal", "sessions", _safe_component(session_id, "session_id"), "cache")

    def session_temp_root(self, session_id: str) -> Path:
        return _resolve_under(self.data_root, "portal", "sessions", _safe_component(session_id, "session_id"), "temp")

    def recovery_root(self, session_id: str) -> Path:
        return _resolve_under(self.data_root, "portal", "recovery", _safe_component(session_id, "session_id"))

    def current_data_root(self, installation_id: str) -> Path:
        return _resolve_under(
            self.data_root,
            "portal",
            "data",
            _safe_component(installation_id, "installation_id"),
            "current",
        )

    def snapshot_root(self, installation_id: str, snapshot_id: str) -> Path:
        return _resolve_under(
            self.data_root,
            "portal",
            "data",
            _safe_component(installation_id, "installation_id"),
            "snapshots",
            _safe_component(snapshot_id, "snapshot_id"),
        )
