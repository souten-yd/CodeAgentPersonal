from __future__ import annotations

from agent.atlas_code_intel_schema import AtlasDependencyGraphRequest, AtlasRelatedTestsRequest, AtlasSymbolIndexRequest
from agent.atlas_code_intel_service import AtlasCodeIntelService
from agent.atlas_git_inspection_service import AtlasGitInspectionService
from agent.atlas_project_inspection_service import AtlasProjectInspectionService


def collect_git_context(project_path: str, changed_files: list[str], limits: dict) -> dict:
    g = AtlasGitInspectionService()
    p = AtlasProjectInspectionService()
    status = g.git_status(project_path)
    diffs = [g.git_diff(project_path, relative_path=path, max_bytes=int(limits.get("max_bytes", 100000))) for path in changed_files[: int(limits.get("max_changed_files", 20))]]
    tree = p.project_tree(project_path, max_files=int(limits.get("max_files", 200)))
    outlines = [p.file_outline(project_path, relative_path=path, max_bytes=int(limits.get("max_bytes", 100000))) for path in changed_files[: int(limits.get("max_changed_files", 20))]]
    return {"status": status, "diffs": diffs, "tree": tree, "outlines": outlines}


def collect_code_intel_context(project_path: str, changed_files: list[str], limits: dict) -> dict:
    svc = AtlasCodeIntelService()
    symbol_index = svc.build_symbol_index(AtlasSymbolIndexRequest(project_path=project_path, max_files=int(limits.get("max_files", 200)), max_symbols=int(limits.get("max_symbols", 1000))))
    dep_graph = svc.build_dependency_graph(AtlasDependencyGraphRequest(project_path=project_path, max_files=int(limits.get("max_files", 200)), max_edges=int(limits.get("max_edges", 800))))
    related_tests = svc.find_related_tests(AtlasRelatedTestsRequest(project_path=project_path, changed_files=changed_files, max_tests=int(limits.get("max_tests", 100))))
    return {"symbol_index": symbol_index, "dependency_graph": dep_graph, "related_tests": related_tests}
