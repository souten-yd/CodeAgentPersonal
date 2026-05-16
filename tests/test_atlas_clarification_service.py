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
