from __future__ import annotations

from typing import Callable


class NexusContextBuilder:
    """Phase 1 minimal nexus context builder.

    - Never raises to caller.
    - Returns empty-but-valid context when unavailable.
    """

    def __init__(
        self,
        memory_search_fn: Callable[[str, int], list] | None = None,
        active_skills_fn: Callable[[], list] | None = None,
        warning_logger: Callable[[str], None] | None = None,
    ) -> None:
        self.memory_search_fn = memory_search_fn
        self.active_skills_fn = active_skills_fn
        self.warning_logger = warning_logger

    def build(self, user_input: str, use_nexus: bool = True) -> dict:
        if not use_nexus:
            return {
                "available": False,
                "summary": "Nexus context is disabled. Continue with empty context.",
                "items": [],
                "warnings": ["Nexus usage disabled by request."],
            }

        warnings: list[str] = []
        items: list[dict] = []
        try:
            if callable(self.memory_search_fn):
                memory_hits = self.memory_search_fn(user_input, limit=3) or []
                for hit in memory_hits:
                    items.append({
                        "type": "memory",
                        "title": str(hit.get("title", "")),
                        "content": str(hit.get("content", ""))[:300],
                    })
            if callable(self.active_skills_fn):
                for skill in (self.active_skills_fn() or [])[:5]:
                    items.append({
                        "type": "skill",
                        "name": str(skill.get("name", "")),
                        "description": str(skill.get("description", ""))[:160],
                    })
        except Exception as exc:  # noqa: BLE001
            msg = f"Nexus context build warning: {exc}"
            warnings.append(msg)
            if callable(self.warning_logger):
                self.warning_logger(msg)

        if not items:
            if not warnings:
                warnings.append("Nexus is not configured or no related memory was found.")
            return {
                "available": False,
                "summary": "Nexus context is not available. Continue with empty context.",
                "items": [],
                "warnings": warnings,
            }

        return {
            "available": True,
            "summary": f"Collected {len(items)} context item(s) from Memory/Skills.",
            "items": items,
            "warnings": warnings,
        }
