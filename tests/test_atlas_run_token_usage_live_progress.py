import json
from pathlib import Path
from types import SimpleNamespace

from agent.atlas_run_schema import AtlasRunState
from agent.atlas_run_store import AtlasRunStore
from app.api.atlas_runs import _run_token_usage


def _fake_request() -> SimpleNamespace:
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))


def _running_state(**overrides) -> AtlasRunState:
    defaults = dict(
        run_id="run_1", pool_id="pool_1", workspace_id="default", status="running",
        phase="proposal", current_item_id="step_1", current_item_index=0, total_items=1,
    )
    defaults.update(overrides)
    return AtlasRunState(**defaults)


def test_run_token_usage_reads_live_patchgen_job_while_item_is_actively_generating(tmp_path: Path):
    # Reproduces the reported bug: the resource/token indicator during an active generation
    # showed 0 the whole time, even though the model was genuinely streaming output. The run's
    # own event log only records coarse lifecycle events (patch_proposal_started/completed) with
    # no per-token data in between, so _run_token_usage fell through to stale/empty metadata.
    # The per-token progress IS available the whole time in the patchgen job file (confirmed live
    # against the real local model: 0 -> 107 -> 410 -> 721 -> ... while generating), just unread.
    store = AtlasRunStore(tmp_path)
    state = store.create_run(pool_id="pool_1", workspace_id="default", run_id="run_1", total_items=1)
    state = store.patch_state(state.run_id, {"status": "running", "current_item_id": "step_1"})

    jobs_dir = tmp_path / "atlas" / "patchgen_jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    (jobs_dir / "pool_1__step_1.json").write_text(
        json.dumps({
            "pool_id": "pool_1", "item_id": "step_1", "status": "running",
            "tokens_generated": 721, "last_token_at": "2026-07-09T23:56:31Z",
        }),
        encoding="utf-8",
    )

    usage = _run_token_usage(store, state, _fake_request(), pool=None, root_dir=tmp_path)

    assert usage["generated_tokens"] == 721
    assert usage["tokens_generated"] == 721


def test_run_token_usage_falls_back_when_no_live_job_present(tmp_path: Path):
    # No active generation for this item: must not error, and should not fabricate a count.
    store = AtlasRunStore(tmp_path)
    state = store.create_run(pool_id="pool_1", workspace_id="default", run_id="run_1", total_items=1)

    usage = _run_token_usage(store, state, _fake_request(), pool=None, root_dir=tmp_path)

    assert usage["generated_tokens"] == 0
    assert usage["tokens_generated"] == 0


def test_run_token_usage_ignores_a_completed_job_file(tmp_path: Path):
    # A job file left over from a PRIOR completed/failed item must not be reported as live
    # progress for the run's CURRENT item.
    store = AtlasRunStore(tmp_path)
    state = store.create_run(pool_id="pool_1", workspace_id="default", run_id="run_1", total_items=1)
    state = store.patch_state(state.run_id, {"status": "running", "current_item_id": "step_1"})

    jobs_dir = tmp_path / "atlas" / "patchgen_jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    (jobs_dir / "pool_1__step_1.json").write_text(
        json.dumps({"pool_id": "pool_1", "item_id": "step_1", "status": "done", "tokens_generated": 5000}),
        encoding="utf-8",
    )

    usage = _run_token_usage(store, state, _fake_request(), pool=None, root_dir=tmp_path)

    assert usage["generated_tokens"] == 0
