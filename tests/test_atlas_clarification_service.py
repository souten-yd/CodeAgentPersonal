from pathlib import Path

from agent.atlas_clarification_schema import AtlasClarificationAnswer
from agent.atlas_clarification_service import AtlasClarificationService
from agent.atlas_journal import AtlasJournal


def test_create_session_from_plan_response_creates_session(tmp_path):
    svc = AtlasClarificationService(journal=AtlasJournal(tmp_path, workspace_id='default'))
    session = svc.create_session_from_plan_response('goal', {'questions':[{'question_id':'q1','prompt':'p'}], 'requirement':{}}, {'workspace_id':'default'})
    assert session.session_id
    assert session.status == 'waiting_for_clarification'


def test_merge_answers_into_input_appends_clarification_answers():
    svc = AtlasClarificationService()
    text = svc.merge_answers_into_input('goal', [{'question_id':'q1','prompt':'Pick'}], [AtlasClarificationAnswer(question_id='q1', answer='A')])
    assert 'Clarification answers' in text and 'Pick: A' in text


def test_skipped_answers_are_recorded_as_assumptions():
    svc = AtlasClarificationService()
    text = svc.merge_answers_into_input('goal', [{'question_id':'q1','prompt':'Pick'}], [AtlasClarificationAnswer(question_id='q1', skipped=True)])
    assert 'skipped / use assumptions' in text


def test_merge_answers_into_requirement_adds_answered_questions():
    svc = AtlasClarificationService()
    req = svc.merge_answers_into_requirement({'open_questions':[{'question_id':'q1'}]}, [AtlasClarificationAnswer(question_id='q1', answer='x')])
    assert req['answered_questions'][0]['question_id'] == 'q1'
    assert req['open_questions'] == []


def test_build_question_queue_creates_independent_questions():
    svc = AtlasClarificationService()
    questions = svc.build_question_queue(
        ambiguity_signals=["scope not defined"],
        options=[
            {"option_id": "missing_steps", "label": "missing_steps", "description": "Need implementation steps"},
            {"option_id": "maintainability", "label": "maintainability", "description": "Need simpler structure"},
        ],
    )
    assert [q["question_id"] for q in questions] == ["clar_q_1", "clar_q_2", "clar_q_3"]
    assert [q["index"] for q in questions] == [1, 2, 3]
    assert all(q["total"] == 3 for q in questions)
    assert all(len(q["options"]) >= 4 for q in questions)
    assert all(any(o["option_id"] == "custom" and o.get("requires_text") for o in q["options"]) for q in questions)
    assert questions[0]["title"] != "Clarify missing_steps"
    assert questions[0]["user_facing_issue_summary"]
    assert questions[0]["why_it_matters"]
    assert questions[0]["detected_signal_metadata"]["raw_label"] == "missing_steps"
    assert questions[0]["remediation_options_generated_by"] == "template_fallback"
    for option in questions[0]["options"]:
        assert "plan_change_summary" in option
        assert "implementation_scope" in option
        assert "risk_level" in option
        assert option["gate_rerun_required"] is True
        assert option["can_continue_after_answer"] is False
        assert "requires_text" in option


def test_missing_game_over_question_uses_concrete_remediation_options():
    svc = AtlasClarificationService()
    questions = svc.build_question_queue(
        options=[
            {
                "option_id": "missing_steps",
                "label": "missing_steps",
                "description": "Game plan lacks game-over, collision restart, and animation loop behavior.",
            }
        ],
    )

    question = questions[0]
    assert question["title"] == "Game-over and restart behavior is missing"
    assert "how the game ends" in question["user_facing_issue_summary"]
    assert "restart state" in question["why_it_matters"]
    labels = [option["label"] for option in question["options"]]
    assert labels[:3] == ["Recommended safe fix", "Minimal fix", "Defer/remove"]
    assert "playing -> game_over -> restart" in question["options"][0]["plan_change_summary"]
    assert question["recommended_option_id"] == "safest_recommended"
    assert all("requires_text" in option for option in question["options"])


def test_apply_answer_marks_only_one_question_answered():
    svc = AtlasClarificationService()
    questions = svc.build_question_queue(
        options=[
            {"option_id": "missing_steps", "label": "missing_steps", "description": "Need implementation steps"},
            {"option_id": "maintainability", "label": "maintainability", "description": "Need simpler structure"},
            {"option_id": "requirement_alignment", "label": "requirement_alignment", "description": "Need requirement fit"},
        ],
    )
    progress = svc.apply_answer_to_question_queue(
        questions=questions,
        question_id="clar_q_1",
        option_id="minimal_scope",
        answer_text="Keep one file",
    )
    assert progress["answered_count"] == 1
    assert progress["pending_count"] == 2
    assert progress["all_answered"] is False
    assert progress["questions"][0]["status"] == "answered"
    assert progress["questions"][1]["status"] == "pending"
    assert progress["answers"][0]["question_id"] == "clar_q_1"
    assert progress["answers"][0]["selected_option_impact"]["implementation_scope"] == "minimal"


def test_save_load_session_with_journal(tmp_path):
    journal = AtlasJournal(tmp_path, workspace_id='default')
    svc = AtlasClarificationService(journal=journal)
    s = svc.create_session_from_plan_response('goal', {'questions':[], 'requirement':{}}, {'workspace_id':'default'})
    path = svc.save_session(s)
    assert Path(path).exists()
    loaded = svc.load_session(s.session_id, 'default')
    assert loaded and loaded.session_id == s.session_id


def test_service_has_no_execution_side_effect_tokens():
    src = Path('agent/atlas_clarification_service.py').read_text(encoding='utf-8')
    for forbidden in ['safe_apply(', 'TestCommandRunner(', 'DebugLoopRunner(', 'DeepResearch', 'subprocess']:
        assert forbidden not in src
