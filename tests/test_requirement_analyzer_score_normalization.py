from agent.requirement_analyzer import RequirementAnalyzer, _score


def test_requirement_analyzer_accepts_label_scores() -> None:
    def fake_llm(_prompt, _input):
        return {
            "interpreted_goal": "test",
            "functional_requirements": ["do task"],
            "done_definition": ["done"],
            "requirement_completeness_score": "high",
            "category_scores": {
                "goal": "high",
                "scope": "medium",
                "functional_requirements": "70%",
                "non_functional_requirements": "0.7/1.0",
                "constraints": 70,
                "done_definition": "low",
            },
        }

    analyzer = RequirementAnalyzer(fake_llm)
    req = analyzer.analyze(
        source_task_id="t1",
        user_input="analyze scope and impacted components",
        requirement_mode="ask_when_needed",
        planning_mode="standard",
        prompt="test",
        nexus_context={},
        repository_context="",
    )

    assert 0.8 <= req.category_scores.goal <= 0.9
    assert 0.55 <= req.category_scores.scope <= 0.65
    assert 0.65 <= req.category_scores.functional_requirements <= 0.75
    assert 0.65 <= req.category_scores.non_functional_requirements <= 0.75
    assert 0.65 <= req.category_scores.constraints <= 0.75
    assert 0.3 <= req.category_scores.done_definition <= 0.4
    assert 0.8 <= req.requirement_completeness_score <= 0.9


def test_score_normalizes_supported_llm_score_shapes() -> None:
    assert _score("high", 0.65) == 0.85
    assert _score("medium", 0.65) == 0.6
    assert _score("low", 0.65) == 0.35
    assert _score("unknown", 0.65) == 0.65
    assert _score("70%", 0.65) == 0.7
    assert _score("0.7/1.0", 0.65) == 0.7
    assert _score(70, 0.65) == 0.7
    assert _score(True, 0.65) == 1.0
    assert _score(False, 0.65) == 0.0
    assert _score(None, 0.65) == 0.65
    assert _score("abc", 0.65) == 0.65


def test_requirement_analyzer_falls_back_for_invalid_scores() -> None:
    def fake_llm(_prompt, _input):
        return {
            "interpreted_goal": "test",
            "functional_requirements": ["do task"],
            "done_definition": ["done"],
            "requirement_completeness_score": "abc",
            "category_scores": {
                "goal": "abc",
                "scope": None,
                "functional_requirements": True,
                "non_functional_requirements": False,
                "constraints": 0,
                "done_definition": 1,
            },
        }

    analyzer = RequirementAnalyzer(fake_llm)
    req = analyzer.analyze(
        source_task_id="t1",
        user_input="analyze scope and impacted components",
        requirement_mode="ask_when_needed",
        planning_mode="standard",
        prompt="test",
        nexus_context={},
        repository_context="",
    )

    assert req.requirement_completeness_score == 0.65
    assert req.category_scores.goal == 0.7
    assert req.category_scores.scope == 0.6
    assert req.category_scores.functional_requirements == 1.0
    assert req.category_scores.non_functional_requirements == 0.0
    assert req.category_scores.constraints == 0.0
    assert req.category_scores.done_definition == 1.0


def test_requirement_analyzer_preserves_codegen_contract_fields() -> None:
    def fake_llm(_prompt, _input):
        return {
            "interpreted_goal": "Build score",
            "functional_requirements": ["Score increments"],
            "requirements": [{"requirement_id": "req_score", "description": "Score increments"}],
            "done_definition": ["Done"],
            "acceptance_criteria": ["Score visible"],
            "verification_contract": {"contract_id": "browser_dom"},
            "expected_changes": ["Update score UI"],
            "preserve_behaviors": ["Keep reset"],
            "selected_architecture": "Use existing UI module",
        }

    analyzer = RequirementAnalyzer(fake_llm)
    req = analyzer.analyze(
        source_task_id="t1",
        user_input="Create score",
        requirement_mode="ask_when_needed",
        planning_mode="standard",
        prompt="test",
        nexus_context={},
        repository_context="",
    )

    assert req.requirement_items[0]["requirement_id"] == "req_score"
    assert req.acceptance_criteria == ["Score visible"]
    assert req.verification_contract["contract_id"] == "browser_dom"
    assert req.expected_changes == ["Update score UI"]
    assert req.preserve_behaviors == ["Keep reset"]
    assert req.selected_architecture == "Use existing UI module"


def test_requirement_analysis_failure_does_not_fabricate_ready_contract() -> None:
    analyzer = RequirementAnalyzer(lambda _prompt, _input: None)

    req = analyzer.analyze(
        source_task_id="t1",
        user_input="Create score",
        requirement_mode="ask_when_needed",
        planning_mode="standard",
        prompt="test",
        nexus_context={},
        repository_context="",
    )

    assert req.analysis_status == "failed"
    assert req.ready_for_planning is False
    assert req.functional_requirements == []
    assert req.done_definition == []
    assert any("Planning is blocked" in warning for warning in req.analysis_warnings)
