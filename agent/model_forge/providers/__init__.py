"""Forge provider implementations.

Provider modules must not import UI modules or FastAPI routers. Each provider wraps a
single execution backend behind the ForgeProvider interface.
"""
from __future__ import annotations

from agent.model_forge.providers.legacy_atlas import (
    LegacyAtlasProvider,
    legacy_atlas_descriptor,
)

__all__ = ["LegacyAtlasProvider", "legacy_atlas_descriptor"]
