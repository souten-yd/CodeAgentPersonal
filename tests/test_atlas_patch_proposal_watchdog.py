"""PG-A watchdog tests: streaming heartbeat, stall detection, ATLAS_LLM_STREAMING=0 fallback, JS contract."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main
from agent.atlas_journal import AtlasJournal
from agent.atlas_llm_json_adapter import AtlasLLMJsonAdapter
from agent.atlas_llm_json_adapter_schema import AtlasLLMJsonRequest
from agent.atlas_patch_proposal_schema import AtlasPatchProposalRequest
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _client(tmp_path: Path) -> TestClient:
    main.app.state.atlas_ca_data_dir = str(tmp_path)
    main.app.state.atlas_llm_json_fn = None
    return TestClient(main.app)


def _create_pool_and_item(c: TestClient) -> tuple[str, str]:
    item = AtlasPlanItem(
        item_id="i1",
        pool_id="p1",
        title="Watchdog test item",
        goal="implement watchdog",
        item_type="implementation",
        status="ready",
        risk_level="low",
        target_files=["out.py"],
        metadata={"action_type": "create", "debug_review": {
            "status": "analyzed",
            "root_cause_category": "test",
            "proposed_fix": "add watchdog",
        }},
    )
    pool = AtlasPlanPool(
        pool_id="p1",
        root_goal="watchdog",
        project_path=str(Path(c.app.state.atlas_ca_data_dir)),
        status="ready",
        items=[item],
    )
    storage = AtlasPlanPoolStorage(Path(c.app.state.atlas_ca_data_dir))
    journal = AtlasJournal(Path(c.app.state.atlas_ca_data_dir), workspace_id="default")
    storage.save_pool(pool)
    journal.save_plan_pool(pool)
    return pool.pool_id, item.item_id


# ---------------------------------------------------------------------------
# PG-A1: streaming on_progress token heartbeat がパッチ生成経路に届く
# ---------------------------------------------------------------------------

def test_patchgen_on_progress_heartbeat_updates_job_file(tmp_path: Path) -> None:
    """on_progress を持つ fake adapter を注入し、job ファイルが last_token_at を持つことを確認。"""
    progress_calls: list[dict] = []

    class FakeAdapter(AtlasLLMJsonAdapter):
        def generate_json(self, request: AtlasLLMJsonRequest):
            # Simulate token emission
            if self.on_progress:
                self.on_progress({"tokens_generated": 5, "last_token_at": "2099-01-01T00:00:00+00:00"})
            from agent.atlas_llm_json_adapter_schema import AtlasLLMJsonResult
            return AtlasLLMJsonResult(ok=True, data={
                "summary": "heartbeat test",
                "proposed_fix": "add heartbeat",
                "target_files": ["out.py"],
                "proposed_content": "# heartbeat",
                "risk_level": "low",
            })

    c = _client(tmp_path)
    c.app.state.atlas_llm_json_fn = FakeAdapter()
    pool_id, item_id = _create_pool_and_item(c)

    resp = c.post("/api/atlas/patch-proposals/generate", json={
        "pool_id": pool_id, "item_id": item_id, "run_id": "r1",
        "source_type": "plan_item",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "proposed"

    # Job ファイルが生成されており done になっていること
    job_path = tmp_path / "atlas" / "patchgen_jobs" / f"{pool_id}__{item_id}.json"
    assert job_path.exists(), "patchgen job file must be written"
    job = json.loads(job_path.read_text(encoding="utf-8"))
    assert job["status"] == "done"
    assert "finished_at" in job


def test_patchgen_job_file_written_on_fallback(tmp_path: Path) -> None:
    """LLM なし(fallback)でもジョブファイルが done になる。"""
    c = _client(tmp_path)
    pool_id, item_id = _create_pool_and_item(c)

    resp = c.post("/api/atlas/patch-proposals/generate", json={
        "pool_id": pool_id, "item_id": item_id, "run_id": "r2",
        "source_type": "debug_review",
    })
    assert resp.status_code == 200

    job_path = tmp_path / "atlas" / "patchgen_jobs" / f"{pool_id}__{item_id}.json"
    assert job_path.exists()
    job = json.loads(job_path.read_text(encoding="utf-8"))
    assert job["status"] == "done"


# ---------------------------------------------------------------------------
# PG-A2: is_stalled 検知 — /patch-proposals/status エンドポイント
# ---------------------------------------------------------------------------

def test_patchgen_status_404_when_not_started(tmp_path: Path) -> None:
    c = _client(tmp_path)
    resp = c.get("/api/atlas/patch-proposals/status?pool_id=p99&item_id=i99")
    assert resp.status_code == 404


def test_patchgen_status_running_not_stalled(tmp_path: Path) -> None:
    c = _client(tmp_path)
    pool_id, item_id = _create_pool_and_item(c)
    # Write a fresh "running" job manually
    jobs_dir = tmp_path / "atlas" / "patchgen_jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    now = "2099-01-01T00:00:00+00:00"
    job_file = jobs_dir / f"{pool_id}__{item_id}.json"
    job_file.write_text(json.dumps({
        "pool_id": pool_id, "item_id": item_id, "status": "running",
        "started_at": now, "last_token_at": now, "tokens_generated": 10,
    }), encoding="utf-8")

    resp = c.get(f"/api/atlas/patch-proposals/status?pool_id={pool_id}&item_id={item_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "running"
    assert data["is_running"] is True
    assert data["is_stalled"] is False


def test_patchgen_status_is_stalled_when_no_progress(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """last_token_at が古ければ is_stalled=True になる。"""
    monkeypatch.setenv("ATLAS_PLAN_STALL_AFTER_SEC", "1")
    c = _client(tmp_path)
    pool_id, item_id = _create_pool_and_item(c)
    jobs_dir = tmp_path / "atlas" / "patchgen_jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    stale_time = "2000-01-01T00:00:00+00:00"
    job_file = jobs_dir / f"{pool_id}__{item_id}.json"
    job_file.write_text(json.dumps({
        "pool_id": pool_id, "item_id": item_id, "status": "running",
        "started_at": stale_time, "last_token_at": stale_time, "tokens_generated": 0,
    }), encoding="utf-8")

    resp = c.get(f"/api/atlas/patch-proposals/status?pool_id={pool_id}&item_id={item_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_stalled"] is True
    assert "stalled_reason" in data and data["stalled_reason"]


def test_patchgen_status_done_is_not_stalled(tmp_path: Path) -> None:
    c = _client(tmp_path)
    pool_id, item_id = _create_pool_and_item(c)
    jobs_dir = tmp_path / "atlas" / "patchgen_jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    job_file = jobs_dir / f"{pool_id}__{item_id}.json"
    stale_time = "2000-01-01T00:00:00+00:00"
    job_file.write_text(json.dumps({
        "pool_id": pool_id, "item_id": item_id, "status": "done",
        "started_at": stale_time, "finished_at": stale_time,
    }), encoding="utf-8")

    resp = c.get(f"/api/atlas/patch-proposals/status?pool_id={pool_id}&item_id={item_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_stalled"] is False
    assert data["is_running"] is False


def test_patchgen_status_rejects_dotdot(tmp_path: Path) -> None:
    c = _client(tmp_path)
    resp = c.get("/api/atlas/patch-proposals/status?pool_id=../evil&item_id=i1")
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# PG-A3: ATLAS_LLM_STREAMING=0 で従来ブロッキング動作（streaming 無効）
# ---------------------------------------------------------------------------

def test_streaming_disabled_by_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """ATLAS_LLM_STREAMING=0 のとき _streaming_enabled が False を返す。"""
    monkeypatch.setenv("ATLAS_LLM_STREAMING", "0")
    adapter = AtlasLLMJsonAdapter(on_progress=lambda p: None)
    req = AtlasLLMJsonRequest(system_prompt="s", user_prompt="u")
    assert adapter._streaming_enabled(req) is False


def test_streaming_enabled_with_on_progress(monkeypatch: pytest.MonkeyPatch) -> None:
    """on_progress が設定されていれば streaming が有効になる。"""
    monkeypatch.delenv("ATLAS_LLM_STREAMING", raising=False)
    adapter = AtlasLLMJsonAdapter(on_progress=lambda p: None)
    req = AtlasLLMJsonRequest(system_prompt="s", user_prompt="u")
    assert adapter._streaming_enabled(req) is True


def test_streaming_disabled_without_on_progress(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ATLAS_LLM_STREAMING", raising=False)
    adapter = AtlasLLMJsonAdapter()
    req = AtlasLLMJsonRequest(system_prompt="s", user_prompt="u")
    assert adapter._streaming_enabled(req) is False


# ---------------------------------------------------------------------------
# Client contract: JS ファイルが stall/絶対上限ベースのパターンを含む
# ---------------------------------------------------------------------------

def test_js_patchgen_client_contract() -> None:
    """generatePatchProposal が PATCHGEN_ABSOLUTE_MAX_MS と patchgen_stalled を使っていること。"""
    js = Path("web/js/atlas_pipeline_api.js").read_text(encoding="utf-8")
    assert "PATCHGEN_ABSOLUTE_MAX_MS" in js, "絶対上限定数が無い"
    assert "patchgen_stalled" in js, "stall エラーコードが無い"
    assert "getPatchGenStatus" in js, "getPatchGenStatus メソッドが無い"
    assert "/api/atlas/patch-proposals/status" in js, "status エンドポイントの URL が無い"
    assert "Promise.race" in js, "Promise.race による stall/generate の race が無い"
    # 固定 120s (DEFAULT_TIMEOUT_MS) を patch generate に使っていないこと
    # generatePatchProposal 内に timeoutMs: PATCHGEN_ABSOLUTE_MAX_MS が存在する
    assert "timeoutMs: PATCHGEN_ABSOLUTE_MAX_MS" in js, "generate リクエストに絶対上限 timeout が設定されていない"
