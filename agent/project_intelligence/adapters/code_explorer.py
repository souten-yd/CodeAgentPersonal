from __future__ import annotations

from agent.atlas_code_explorer import (
    build_research_evidence,
    extract_symbols,
    find_related_tests,
    search_code_excerpts,
)


class ProjectIntelligenceCodeExplorerAdapter:
    """Compatibility adapter for best-effort read-only code exploration."""

    def search_code_excerpts(self, project_path: str, terms: list[str], *, max_hits: int = 20, context_lines: int = 2) -> list[dict]:
        return search_code_excerpts(project_path, terms, max_hits=max_hits, context_lines=context_lines)

    def extract_symbols(self, project_path: str, *, target_files: list[str] | None = None, max_symbols: int = 60) -> list[dict]:
        return extract_symbols(project_path, target_files=target_files, max_symbols=max_symbols)

    def find_related_tests(self, project_path: str, target_files: list[str], *, max_tests: int = 10) -> list[str]:
        return find_related_tests(project_path, target_files, max_tests=max_tests)

    def build_research_evidence(self, project_path: str, *, query_terms: list[str], goal: str) -> dict:
        return build_research_evidence(project_path, query_terms=query_terms, goal=goal)
