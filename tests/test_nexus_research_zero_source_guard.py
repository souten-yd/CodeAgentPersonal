from app.nexus.research_agent import should_expand_retrieval

def test_zero_source_requires_more_rounds():
    summary={"candidate_count":0,"valid_source_count":0,"evidence_count":0,"high_quality_source_count":0,"official_source_count":0,"pdf_source_count":0}
    targets={"max_retrieval_rounds":3,"target_candidate_count":10,"target_valid_source_count":1,"target_evidence_count":1}
    expand,reasons=should_expand_retrieval(summary,targets,0)
    assert expand is True
    assert reasons
