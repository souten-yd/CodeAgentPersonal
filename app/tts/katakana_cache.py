from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

_logger = logging.getLogger("style_bert_vits2")
_DEFAULT_CACHE_PATH = "./ca_data/tts/katakana_cache.json"


@dataclass
class KatakanaCacheEntry:
    source: str
    reading: str
    created_by: str = "llm"
    updated_at: str = ""
    hit_count: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "source": self.source,
            "reading": self.reading,
            "created_by": self.created_by,
            "updated_at": self.updated_at,
            "hit_count": int(self.hit_count),
        }


class KatakanaPersistentCache:
    def __init__(self, path: str | None = None) -> None:
        self._path = Path(path or os.environ.get("CODEAGENT_KATAKANA_CACHE_PATH") or _DEFAULT_CACHE_PATH)
        self._lock = threading.Lock()
        self._entries: dict[str, KatakanaCacheEntry] = {}
        self._loaded = False

    @staticmethod
    def normalize_key(token: str | None) -> str:
        return str(token or "").strip().lower()

    def get(self, token: str) -> str | None:
        key = self.normalize_key(token)
        if not key:
            return None
        with self._lock:
            self._ensure_loaded_locked()
            entry = self._entries.get(key)
            if not entry:
                return None
            entry.hit_count += 1
            entry.updated_at = _utc_now()
            self._save_locked()
            return entry.reading

    def set(self, token: str, reading: str, *, created_by: str = "llm") -> None:
        key = self.normalize_key(token)
        if not key:
            return
        with self._lock:
            self._ensure_loaded_locked()
            prev = self._entries.get(key)
            self._entries[key] = KatakanaCacheEntry(
                source=(prev.source if prev and prev.source else token),
                reading=reading,
                created_by=created_by,
                updated_at=_utc_now(),
                hit_count=(prev.hit_count if prev else 0),
            )
            self._save_locked()

    def _ensure_loaded_locked(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            if not self._path.exists():
                self._save_locked()
                return
            with self._path.open("r", encoding="utf-8") as fh:
                payload = json.load(fh)
            entries = payload.get("entries", {}) if isinstance(payload, dict) else {}
            for key, raw in entries.items():
                if not isinstance(raw, dict):
                    continue
                norm_key = self.normalize_key(key)
                if not norm_key:
                    continue
                reading = str(raw.get("reading") or "").strip()
                if not reading:
                    continue
                self._entries[norm_key] = KatakanaCacheEntry(
                    source=str(raw.get("source") or key),
                    reading=reading,
                    created_by=str(raw.get("created_by") or "llm"),
                    updated_at=str(raw.get("updated_at") or ""),
                    hit_count=int(raw.get("hit_count") or 0),
                )
        except Exception as exc:
            _logger.warning("[SBV2][normalize][persistent_cache_load_failed] path=%s reason=%s", self._path, exc)
            try:
                if self._path.exists():
                    self._path.replace(self._path.with_suffix(self._path.suffix + ".bak"))
            except Exception:
                pass
            self._entries = {}

    def _save_locked(self) -> None:
        payload = {"entries": {key: entry.to_dict() for key, entry in sorted(self._entries.items())}}
        tmp_path = self._path.with_suffix(self._path.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        tmp_path.replace(self._path)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
