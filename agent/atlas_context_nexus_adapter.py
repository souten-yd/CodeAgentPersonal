from __future__ import annotations

from agent.atlas_context_refresh_schema import AtlasContextSource


class AtlasContextNexusAdapter:
    def search_local(self, query: str, max_sources: int) -> tuple[list[AtlasContextSource], list[str]]:
        return [], ["nexus_local_unavailable"]

    def search_web(self, query: str, max_sources: int) -> tuple[list[AtlasContextSource], list[str]]:
        return [], ["nexus_web_unavailable"]

    def start_deep_research(self, query: str, budget: dict) -> tuple[list[AtlasContextSource], list[str]]:
        return [], ["nexus_deep_research_unavailable"]
