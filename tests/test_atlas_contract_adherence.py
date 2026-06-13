"""② Contract-adherence: a FULL-content rewrite that drops a contract entity already wired in the
prior content is flagged (integration regression), while edits and new files are not."""
from agent.atlas_interface_contract import app_is_interface_coupled, render_contract_for_prompt
from agent.atlas_journal import AtlasJournal
from agent.atlas_patch_proposal_service import AtlasPatchProposalService
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage


def _service(tmp_path):
    return AtlasPatchProposalService(journal=AtlasJournal(tmp_path / "ca"), storage=AtlasPlanPoolStorage(tmp_path / "ca"), llm_json_fn=None)


_CONTRACT = {"entities": [{"name": "enemyManager"}, {"name": "player"}, {"name": "bullet"}]}


def test_dropped_contract_entity_is_flagged(tmp_path):
    svc = _service(tmp_path)
    payload = {
        "app_interface_contract": _CONTRACT,
        "current_target_contents": {"index.html": {"content": "const player={}; const enemyManager={}; const bullet={};"}},
    }
    # Full rewrite that LOST enemyManager (no mention of it anywhere in the new content).
    content_by_path = {"index.html": "const player={}; const bullet={}; const score=0;"}
    metadata = {"proposed_content": content_by_path["index.html"]}
    out = svc._contract_adherence_advisories(payload, content_by_path, metadata)
    assert "contract_entity_dropped:enemyManager" in out
    assert "contract_entity_dropped:player" not in out


def test_no_flag_when_all_entities_preserved(tmp_path):
    svc = _service(tmp_path)
    payload = {
        "app_interface_contract": _CONTRACT,
        "current_target_contents": {"index.html": {"content": "const player={}; const enemyManager={}; const bullet={};"}},
    }
    content_by_path = {"index.html": "const player={}; const enemyManager={}; const bullet={}; const score=0;"}
    out = svc._contract_adherence_advisories(payload, content_by_path, {"proposed_content": content_by_path["index.html"]})
    assert out == []


def test_edits_are_not_checked(tmp_path):
    # Surgical edits preserve surroundings; the partial new_string must NOT be treated as the whole file.
    svc = _service(tmp_path)
    payload = {
        "app_interface_contract": _CONTRACT,
        "current_target_contents": {"index.html": {"content": "const player={}; const enemyManager={}; const bullet={};"}},
    }
    content_by_path = {"index.html": "const score=0;"}  # an edit snippet, not the full file
    out = svc._contract_adherence_advisories(payload, content_by_path, {"edits": [{"old_string": "a", "new_string": "const score=0;"}]})
    assert out == []  # no proposed_content / full_content -> skipped


def test_new_file_is_not_flagged(tmp_path):
    svc = _service(tmp_path)
    payload = {"app_interface_contract": _CONTRACT, "current_target_contents": {}}
    out = svc._contract_adherence_advisories(payload, {"index.html": "const player={};"}, {"proposed_content": "const player={};"})
    assert out == []


def test_interface_coupled_detection_and_render():
    class _It:
        def __init__(self, tf):
            self.target_files = tf
    assert app_is_interface_coupled([_It(["index.html"]), _It(["index.html"])]) is True
    assert app_is_interface_coupled([_It(["a.py"]), _It(["b.py"])]) is False
    rendered = render_contract_for_prompt({"entities": [{"name": "player", "methods": ["update()", "draw(ctx)"]}], "wiring": "loop calls player.update then player.draw"})
    assert "player" in rendered and "WIRING" in rendered
