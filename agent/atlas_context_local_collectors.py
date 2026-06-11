from __future__ import annotations

from agent.atlas_code_intel_schema import AtlasDependencyGraphRequest, AtlasRelatedTestsRequest, AtlasSymbolIndexRequest
from agent.project_intelligence.adapters.atlas_inspection import AtlasInspectionAdapter
from agent.project_intelligence.adapters.code_intel import ProjectIntelligenceCodeIntelAdapter


def collect_git_context(project_path: str, changed_files: list[str], limits: dict) -> dict:
    inspection = AtlasInspectionAdapter()
    warnings: list[str] = []
    status = None
    diffs = []
    tree = None
    outlines = []

    try:
        status = inspection.git_status(project_path)
    except Exception:
        warnings.append("git_status_unavailable")

    for path in changed_files[: int(limits.get("max_changed_files", 20))]:
        try:
            diffs.append(
                inspection.git_diff(project_path, relative_path=path, max_bytes=int(limits.get("max_bytes", 100000)))
            )
        except Exception:
            warnings.append(f"git_diff_unavailable:{path}")

    try:
        tree = inspection.project_tree(project_path, max_files=int(limits.get("max_files", 200)))
    except Exception:
        warnings.append("project_tree_unavailable")

    for path in changed_files[: int(limits.get("max_changed_files", 20))]:
        try:
            outlines.append(
                inspection.file_outline(
                    project_path,
                    relative_path=path,
                    max_bytes=int(limits.get("max_bytes", 100000)),
                )
            )
        except Exception:
            warnings.append(f"file_outline_unavailable:{path}")

    return {"status": status, "diffs": diffs, "tree": tree, "outlines": outlines, "warnings": warnings}


def collect_code_intel_context(project_path: str, changed_files: list[str], limits: dict) -> dict:
    svc = ProjectIntelligenceCodeIntelAdapter()
    warnings: list[str] = []
    symbol_index = None
    dep_graph = None
    related_tests = None

    try:
        symbol_index = svc.build_symbol_index(AtlasSymbolIndexRequest(project_path=project_path, max_files=int(limits.get("max_files", 200)), max_symbols=int(limits.get("max_symbols", 1000))))
    except Exception:
        warnings.append("symbol_index_unavailable")

    try:
        dep_graph = svc.build_dependency_graph(AtlasDependencyGraphRequest(project_path=project_path, max_files=int(limits.get("max_files", 200)), max_edges=int(limits.get("max_edges", 800))))
    except Exception:
        warnings.append("dependency_graph_unavailable")

    try:
        related_tests = svc.find_related_tests(AtlasRelatedTestsRequest(project_path=project_path, changed_files=changed_files, max_tests=int(limits.get("max_tests", 100))))
    except Exception:
        warnings.append("related_tests_unavailable")

    return {"symbol_index": symbol_index, "dependency_graph": dep_graph, "related_tests": related_tests, "warnings": warnings}
