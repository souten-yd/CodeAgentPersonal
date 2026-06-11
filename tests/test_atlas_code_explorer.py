"""Pillar C: code exploration — real code excerpts, symbols, related tests reach the planner/patch gen."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from agent.project_intelligence.adapters.code_explorer import (
    build_research_evidence,
    extract_symbols,
    find_related_tests,
    search_code_excerpts,
)
from agent.research_conductor import ResearchConductor


def _project():
    tmp = Path(tempfile.mkdtemp())
    (tmp / "app.py").write_text(
        "import os\n\ndef greet(name):\n    return f'hi {name}'\n\nclass Service:\n    def run(self):\n        return greet('x')\n",
        encoding="utf-8",
    )
    (tmp / "util.js").write_text("function helper(x){return x+1}\nconst run = async () => helper(2)\n", encoding="utf-8")
    (tmp / "tests").mkdir()
    (tmp / "tests" / "test_app.py").write_text("from app import greet\ndef test_greet():\n    assert greet('a')\n", encoding="utf-8")
    return tmp


def test_search_returns_real_excerpts_with_location():
    tmp = _project()
    hits = search_code_excerpts(str(tmp), ["greet"], max_hits=5)
    assert hits and hits[0]["file"] == "app.py"
    assert any("def greet" in h["excerpt"] for h in hits)
    assert all("line" in h and h["line"] > 0 for h in hits)


def test_extract_symbols_python_and_js():
    tmp = _project()
    py = extract_symbols(str(tmp), target_files=["app.py"])
    names = {s["name"]: s for s in py}
    assert "greet" in names and names["greet"]["signature"] == "def greet(name)"
    assert "Service" in names and names["Service"]["kind"] == "class"
    js = extract_symbols(str(tmp), target_files=["util.js"])
    assert {"helper", "run"} <= {s["name"] for s in js}


def test_find_related_tests_by_basename():
    tmp = _project()
    assert find_related_tests(str(tmp), ["app.py"]) == ["tests/test_app.py"]
    assert find_related_tests(str(tmp), ["unrelated.py"]) == []


def test_build_research_evidence_has_symbols_and_excerpts():
    tmp = _project()
    ev = build_research_evidence(str(tmp), query_terms=["greet"], goal="add farewell")
    assert ev["available"] is True
    assert ev["file_count"] >= 3
    assert "def greet" in ev["text"]
    assert any(s["name"] == "greet" for s in ev["symbols"])


def test_explorer_degrades_on_missing_dir():
    assert build_research_evidence("/no/such/dir", query_terms=["x"], goal="y")["available"] is False
    assert search_code_excerpts("/no/such/dir", ["x"]) == []
    assert extract_symbols("/no/such/dir") == []
    assert find_related_tests("/no/such/dir", ["a.py"]) == []


def test_research_conductor_injects_real_code_evidence():
    tmp = _project()
    seen = {}

    def fake_llm(system, user):
        payload = json.loads(user)
        seen["has_evidence"] = bool(payload.get("code_evidence"))
        seen["has_symbol"] = "greet" in (payload.get("code_evidence") or "")
        return {"key_findings": ["reuse greet"], "relevant_files": ["app.py"]}

    out = ResearchConductor(llm_json_fn=fake_llm).conduct(
        user_input="add feature", interpreted_goal="add feature", repository_context="x", nexus_text="", project_path=str(tmp))
    assert seen["has_evidence"] is True
    assert seen["has_symbol"] is True
    assert out.key_findings == ["reuse greet"]


def test_research_conductor_without_project_path_is_safe():
    seen = {}

    def fake_llm(system, user):
        seen["evidence"] = json.loads(user).get("code_evidence")
        return {"key_findings": ["ok"]}

    out = ResearchConductor(llm_json_fn=fake_llm).conduct(
        user_input="x", interpreted_goal="x", repository_context="r", nexus_text="", project_path="")
    assert seen["evidence"] == ""
    assert "code_evidence_unavailable" in out.warnings
