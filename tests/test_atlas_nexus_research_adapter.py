from __future__ import annotations

import json
from pathlib import Path

from agent.atlas_journal import AtlasJournal
from agent.atlas_nexus_research_adapter import AtlasNexusResearchAdapter
from agent.atlas_nexus_research_schema import AtlasContextFinding, AtlasNexusResearchRequest
from agent.atlas_plan_pool_schema import AtlasPlanItem


def make_request(query: str = "Find context") -> AtlasNexusResearchRequest:
    return AtlasNexusResearchRequest(
        pool_id="pool_1",
        item_id="item_1",
        purpose="codebase_context",
        query=query,
    )


def test_empty_context_pack_when_no_client() -> None:
    adapter = AtlasNexusResearchAdapter(nexus_client=None)

    context_pack = adapter.run_research(make_request("Find implementation context"))

    assert context_pack.status == "completed_with_warnings"
    assert context_pack.insufficient_context is True
    assert "nexus_client_unavailable" in context_pack.warnings


def test_empty_context_pack_when_query_empty() -> None:
    adapter = AtlasNexusResearchAdapter(nexus_client=object())

    context_pack = adapter.run_research(make_request(""))

    assert context_pack.status == "completed_with_warnings"
    assert context_pack.insufficient_context is True
    assert "empty_query" in context_pack.warnings


def test_run_research_uses_client_run_research() -> None:
    class FakeNexusClient:
        def run_research(self, request: AtlasNexusResearchRequest) -> dict:
            return {
                "summary": f"Summary for {request.query}",
                "findings": [{"finding_type": "codebase", "title": "Adapter", "content": "Found adapter context"}],
                "confidence": 0.8,
            }

    adapter = AtlasNexusResearchAdapter(nexus_client=FakeNexusClient())

    context_pack = adapter.run_research(make_request("adapter"))

    assert context_pack.status == "completed"
    assert context_pack.summary == "Summary for adapter"
    assert context_pack.findings[0].finding_type == "codebase"
    assert context_pack.findings[0].title == "Adapter"
    assert context_pack.confidence == 0.8


def test_run_research_falls_back_to_search() -> None:
    class FakeNexusClient:
        def search(self, query: str, max_sources: int) -> dict:
            return {
                "summary": f"Search {query} / {max_sources}",
                "findings": ["search finding"],
                "sources": [{"source_id": "source_1"}],
            }

    adapter = AtlasNexusResearchAdapter(nexus_client=FakeNexusClient())

    context_pack = adapter.run_research(make_request("fallback"))

    assert context_pack.summary == "Search fallback / 10"
    assert context_pack.findings[0].title == "search finding"
    assert context_pack.sources == [{"source_id": "source_1"}]


def test_run_research_handles_client_exception_as_warning_pack() -> None:
    class FakeNexusClient:
        def run_research(self, request: AtlasNexusResearchRequest) -> dict:
            raise RuntimeError("boom")

    adapter = AtlasNexusResearchAdapter(nexus_client=FakeNexusClient())

    context_pack = adapter.run_research(make_request("explode"))

    assert context_pack.status == "completed_with_warnings"
    assert context_pack.insufficient_context is True
    assert any(warning.startswith("nexus_research_failed:") for warning in context_pack.warnings)
    assert any("boom" in warning for warning in context_pack.warnings)


def test_build_context_pack_from_dict_findings() -> None:
    adapter = AtlasNexusResearchAdapter()

    context_pack = adapter.build_context_pack_from_result(
        make_request(),
        {
            "findings": [
                {
                    "finding_type": "technical_spec",
                    "title": "Spec",
                    "content": "Structured context",
                    "confidence": 0.7,
                }
            ]
        },
    )

    assert isinstance(context_pack.findings[0], AtlasContextFinding)
    assert context_pack.findings[0].finding_type == "technical_spec"
    assert context_pack.findings[0].content == "Structured context"
    assert context_pack.summary == "Spec"


def test_build_context_pack_from_string_findings() -> None:
    adapter = AtlasNexusResearchAdapter()

    context_pack = adapter.build_context_pack_from_result(make_request(), {"findings": ["abc"]})

    assert context_pack.findings[0].finding_type == "other"
    assert context_pack.findings[0].title == "abc"
    assert context_pack.findings[0].content == "abc"


def test_request_from_plan_item() -> None:
    item = AtlasPlanItem(
        item_id="item_1",
        pool_id="pool_1",
        title="Research title",
        goal="Research goal",
        description="Research description",
        item_type="research",
        risk_level="low",
        target_files=["agent/example.py"],
        done_definition=["Done context"],
        rollback_plan=["Rollback context"],
        linked_plan_id="plan_1",
        linked_requirement_id="req_1",
        linked_run_id="run_1",
    )
    adapter = AtlasNexusResearchAdapter()

    request = adapter.request_from_plan_item(item)

    assert request.pool_id == "pool_1"
    assert request.item_id == "item_1"
    assert request.run_id == "run_1"
    assert request.query == "Research goal"
    assert request.metadata["item_type"] == "research"
    assert request.metadata["risk_level"] == "low"
    assert request.metadata["target_files"] == ["agent/example.py"]
    assert request.metadata["linked_plan_id"] == "plan_1"
    assert request.metadata["linked_requirement_id"] == "req_1"
    assert request.constraints == ["Done context", "Rollback context"]


def test_save_context_pack_with_journal_writes_json_and_markdown(tmp_path: Path) -> None:
    journal = AtlasJournal(tmp_path, workspace_id="ws_1")
    adapter = AtlasNexusResearchAdapter(journal=journal)
    request = make_request("save context")
    context_pack = adapter.build_context_pack_from_result(
        request,
        {
            "summary": "Saved summary",
            "findings": [{"title": "Saved finding", "content": "Saved finding body"}],
        },
    )

    adapter.save_context_pack(context_pack, pool_id="pool_1")

    json_path = tmp_path / "atlas" / "workspaces" / "ws_1" / "plan_pools" / "pool_1" / "context_packs" / f"{context_pack.context_pack_id}.json"
    markdown_path = json_path.with_suffix(".md")
    assert json_path.exists()
    assert markdown_path.exists()
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["summary"] == "Saved summary"
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "Saved summary" in markdown
    assert "Saved finding" in markdown


def test_adapter_has_no_api_web_deep_research_or_runtime_side_effect_tokens() -> None:
    source = Path("agent/atlas_nexus_research_adapter.py").read_text(encoding="utf-8")

    for forbidden in [
        "FastAPI",
        "@app.",
        "requests.",
        "httpx",
        "subprocess",
        "safe_apply",
        "run_command(",
        "DeepResearch",
        "deep_research_job",
        ".unlink(",
    ]:
        assert forbidden not in source
