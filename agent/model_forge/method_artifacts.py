"""Content-addressed artifact storage for MethodAdapter components."""
from __future__ import annotations

import json
from hashlib import sha256
from typing import Protocol


class MethodArtifactStore(Protocol):
    def put(self, kind: str, payload: object) -> str: ...

    def get(self, ref: str) -> object: ...


class InMemoryMethodArtifactStore:
    """Non-persistent store used by component execution and deterministic tests."""

    def __init__(self) -> None:
        self._artifacts: dict[str, object] = {}

    def put(self, kind: str, payload: object) -> str:
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = sha256(f"{kind}\0{encoded}".encode("utf-8")).hexdigest()
        ref = f"memory://method-artifacts/{kind}/{digest}"
        self._artifacts[ref] = payload
        return ref

    def get(self, ref: str) -> object:
        return self._artifacts[ref]
