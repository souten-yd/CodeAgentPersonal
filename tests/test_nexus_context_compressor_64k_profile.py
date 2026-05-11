from app.nexus.context_compressor import build_context_budget, choose_profile_name, compress_global_evidence, stronger_profile


def _budget(ctx: int):
    return build_context_budget(
        max_context_tokens=ctx,
        instruction_tokens_estimate=300,
        question_tokens_estimate=100,
        source_metadata_tokens_estimate=200,
        preferred_profile=choose_profile_name(ctx),
    )


def test_choose_profile_name_64k_contract():
    assert choose_profile_name(65535) == "long_64k"
    assert choose_profile_name(60000) == "long_64k"
    assert choose_profile_name(32768) == "extended_32k"
    assert stronger_profile("long_64k") == "extended_32k"


def test_build_context_budget_64k_contract():
    budget = _budget(65535)
    assert budget.compression_profile == "long_64k"
    assert budget.max_context_tokens == 65535
    assert budget.max_evidence_chunks >= 96
    assert budget.max_evidence_tokens >= 40000
    assert budget.max_chars_per_chunk >= 2400


def test_64k_global_compression_uses_more_chunks_than_32k():
    refs = [
        {"source_id": f"s{i}", "source_type": "web", "title": f"Source {i}", "url": f"https://example.com/{i}"}
        for i in range(80)
    ]
    chunks = [
        {"source_id": f"s{i}", "chunk_id": f"c{i}", "citation_label": f"[S{i+1}]", "quote": f"unique-{i} " + ("alpha beta " * 80)}
        for i in range(80)
    ]
    out32 = compress_global_evidence("alpha beta", refs, chunks, _budget(32768))
    out64 = compress_global_evidence("alpha beta", refs, chunks, _budget(65535))
    assert out32["stats"]["compression_profile"] == "extended_32k"
    assert out64["stats"]["compression_profile"] == "long_64k"
    assert out64["stats"]["chunks_used"] > out32["stats"]["chunks_used"]


def test_quality_ranking_prefers_official_pdf_cited_chunks():
    budget = _budget(65535)
    refs = [
        {"source_id": "low", "source_type": "web", "title": "Blog", "url": "https://blog.example/low", "status": "degraded"},
        {"source_id": "hi", "source_type": "official", "title": "Official PDF", "url": "https://agency.example/report.pdf", "is_official": True, "content_type": "application/pdf"},
    ]
    chunks = [
        {"source_id": "low", "chunk_id": "l1", "quote": "alpha beta " * 40, "status": "degraded"},
        {"source_id": "hi", "chunk_id": "h1", "citation_label": "[S2]", "quote": "alpha beta " * 80, "content_type": "application/pdf", "is_official": True},
    ]
    out = compress_global_evidence("alpha beta", refs, chunks, budget)
    assert out["references"][0]["source_id"] == "hi"
