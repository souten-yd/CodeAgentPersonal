from app.nexus.research_agent import _analyze_research_gaps
from app.nexus.research_gaps import analyze_claim_level_gaps


def test_uncited_assertion_is_unsupported():
    analysis = analyze_claim_level_gaps({"answer_markdown": "日本では新制度が導入されました。"}, [], [])
    assert "unsupported_claims" in analysis["gaps"]
    assert analysis["unsupported_claim_count"] == 1


def test_citation_matching_reference_without_text_is_weakly_supported():
    analysis = analyze_claim_level_gaps(
        {"answer_markdown": "制度は発表済みです [S1]", "references": [{"citation_label": "[S1]"}]},
        [{"source_id": "src1", "citation_label": "[S1]"}],
        [],
    )
    assert analysis["supported_claim_count"] == 0
    assert analysis["weakly_supported_claim_count"] == 1
    assert "weakly_supported_claims" in analysis["gaps"]
    assert "unsupported_claims" not in analysis["gaps"]


def test_unverified_claim_is_unresolved():
    analysis = analyze_claim_level_gaps({"answer_markdown": "未確認の論点があります。"}, [], [])
    assert "unresolved_claims" in analysis["gaps"]
    assert analysis["unresolved_claim_count"] == 1


def test_single_source_id_is_low_diversity():
    analysis = analyze_claim_level_gaps(
        {"answer_markdown": "発表済みです [S1]", "references": [{"citation_label": "[S1]"}]},
        [{"source_id": "src1", "citation_label": "[S1]"}],
        [],
    )
    assert analysis["low_diversity"] is True
    assert "low_evidence_diversity" in analysis["gaps"]


def test_research_gap_analysis_includes_claim_analysis():
    analysis = _analyze_research_gaps(
        sources=[{"source_id": "src1", "content_type": "application/pdf"}],
        evidence_chunks=[{"source_id": "src1", "citation_label": "[S1]"}],
        answer_payload={"answer_markdown": "発表済みです [S1]", "references": [{"citation_label": "[S1]"}]},
    )
    assert "claim_analysis" in analysis
    assert analysis["claim_analysis"]["claim_count"] >= 1


def test_followup_needed_section_does_not_pollute_claim_counts():
    markdown = """
制度は発表済みです [S1]

## 追加確認が必要な点
- 実施日程の一次資料を確認する
- 対象範囲を確認する

## References
- [S1] source
"""
    analysis = analyze_claim_level_gaps(
        {"answer_markdown": markdown, "references": [{"citation_label": "[S1]"}]},
        [{"source_id": "src1", "citation_label": "[S1]"}],
        [],
    )
    assert analysis["claim_count"] == 1
    assert analysis["weakly_supported_claim_count"] == 1
    assert analysis["unsupported_claim_count"] == 0
    assert "実施日程の一次資料を確認する" in analysis["unresolved_items"]
