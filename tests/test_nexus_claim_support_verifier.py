from app.nexus.research_agent import _generate_followup_queries
from app.nexus.research_gaps import analyze_claim_level_gaps, verify_claim_support


def _claim(text: str) -> dict:
    return {"claim": text, "text": text, "citations": ["[S1]"] if "[S1]" in text else [], "contains_unverified": "未確認" in text}


def test_citation_and_text_supported():
    result = verify_claim_support(
        [_claim("ダイヤモンド半導体は高温環境向けに研究されています [S1]")],
        [{"source_id": "src1", "citation_label": "[S1]", "quote": "高温環境 ダイヤモンド 半導体 研究", "title": "Diamond"}],
        [],
    )
    row = result["claims"][0]
    assert row["status"] == "supported"
    assert row["support_type"] == "citation_and_text"
    assert row["support_score"] > 0


def test_citation_only_weakly_supported():
    result = verify_claim_support(
        [_claim("ダイヤモンド半導体は高温環境向けに研究されています [S1]")],
        [{"source_id": "src1", "citation_label": "[S1]", "quote": "まったく別の市場統計です"}],
        [{"source_id": "src1", "citation_label": "[S1]", "title": "Reference"}],
    )
    row = result["claims"][0]
    assert row["status"] == "weakly_supported"
    assert row["support_type"] == "citation_only"


def test_text_only_supported():
    result = verify_claim_support(
        [_claim("ダイヤモンド半導体は高温環境向けに研究されています")],
        [{"source_id": "src1", "quote": "ダイヤモンド半導体は高温環境向けに研究されています"}],
        [],
    )
    row = result["claims"][0]
    assert row["status"] == "supported"
    assert row["support_type"] == "text_only"


def test_unsupported_without_text_or_citation():
    result = verify_claim_support(
        [_claim("ダイヤモンド半導体は高温環境向けに研究されています")],
        [{"source_id": "src1", "quote": "宇宙天気と農業統計に関する資料"}],
        [],
    )
    row = result["claims"][0]
    assert row["status"] == "unsupported"
    assert row["support_type"] == "none"


def test_unresolved_remains_unresolved():
    result = verify_claim_support(
        [_claim("未確認のダイヤモンド半導体ロードマップがあります [S1]")],
        [{"source_id": "src1", "citation_label": "[S1]", "quote": "ダイヤモンド半導体ロードマップ"}],
        [],
    )
    assert result["claims"][0]["status"] == "unresolved"


def test_analyze_claim_level_gaps_counts_weakly_supported():
    analysis = analyze_claim_level_gaps(
        {"answer_markdown": "ダイヤモンド半導体は高温環境向けに研究されています [S1]", "references": [{"citation_label": "[S1]"}]},
        [{"source_id": "src1", "citation_label": "[S1]", "quote": "無関係な証拠"}],
        [],
    )
    assert analysis["weakly_supported_claim_count"] == 1
    assert "weakly_supported_claims" in analysis["gaps"]


def test_followup_queries_use_unsupported_claim_text():
    queries = _generate_followup_queries(
        original_query="次世代半導体",
        gaps=["unsupported_claims"],
        max_followup_queries=3,
        claim_analysis={
            "claims": [
                {"claim": "ダイヤモンド半導体は高温環境向けに研究されています [S1]", "status": "unsupported"}
            ]
        },
    )
    assert queries
    assert "ダイヤモンド半導体は高温環境向けに研究されています" in queries[0]
    assert "根拠 一次資料" in queries[0]
    assert queries[0] != "次世代半導体 根拠 一次資料 検証"
