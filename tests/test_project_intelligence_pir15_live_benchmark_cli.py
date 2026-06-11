"""PIR-15 live benchmark CLI tests."""

from __future__ import annotations

import json
from pathlib import Path

from agent.project_intelligence.rollout import ENV_ENABLED
from tools import run_pir15_live_benchmark as cli


def _fake_report(status: str, arm: str) -> dict:
    return {
        "status": status,
        "benchmark_arm": arm,
        "started_at": "2026-06-11T00:00:00+00:00",
        "finished_at": "2026-06-11T00:00:01+00:00",
        "independent_acceptance": {"status": "passed" if status == "passed" else "failed"},
        "restart_evidence": {"status": "passed" if status == "passed" else "failed"},
        "steps": [{"name": "plan_pool"}],
        "artifacts": {"index.html": "Atlas Live Greenfield Ready" if status == "passed" else ""},
    }


def test_live_benchmark_cli_runs_legacy_off_and_final_active(tmp_path: Path, monkeypatch) -> None:
    calls: list[dict] = []

    def fake_run(workspace: Path, data_dir: Path, *, arm_name: str, rollout_env: dict[str, str]) -> dict:
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / "index.html").write_text("Atlas Live Greenfield Ready", encoding="utf-8")
        calls.append(
            {
                "workspace": workspace,
                "data_dir": data_dir,
                "arm_name": arm_name,
                "rollout_env": dict(rollout_env),
            }
        )
        return _fake_report("passed", arm_name)

    monkeypatch.setattr(cli, "run_live_greenfield", fake_run)
    output = tmp_path / "benchmark.json"

    report = cli.run_live_comparative_benchmark(
        corpus_path=cli.REPO_ROOT / "docs" / "generated" / "atlas_project_intelligence_pir15_benchmark_corpus.json",
        workspace_root=tmp_path / "workspaces",
        data_root=tmp_path / "data",
        output_json=output,
    )

    assert [call["arm_name"] for call in calls] == ["legacy", "final"]
    assert calls[0]["rollout_env"] == {}
    assert calls[1]["rollout_env"] == {ENV_ENABLED: "1"}
    assert report["arm_statuses"] == {"legacy": "passed", "final": "passed"}
    assert json.loads(output.read_text(encoding="utf-8"))["safety"]["manual_metrics_accepted"] is False


def test_live_benchmark_cli_reports_blocked_without_passing(tmp_path: Path, monkeypatch) -> None:
    def fake_run(workspace: Path, _data_dir: Path, *, arm_name: str, rollout_env: dict[str, str]) -> dict:
        if arm_name == "final":
            workspace.mkdir(parents=True, exist_ok=True)
            (workspace / "index.html").write_text("Atlas Live Greenfield Ready", encoding="utf-8")
        return _fake_report("blocked" if arm_name == "legacy" else "passed", arm_name)

    monkeypatch.setattr(cli, "run_live_greenfield", fake_run)

    exit_code = cli.main_cli(
        [
            "--workspace-root",
            str(tmp_path / "workspaces"),
            "--data-root",
            str(tmp_path / "data"),
            "--output-json",
            str(tmp_path / "benchmark.json"),
            "--allow-blocked-exit-zero",
        ]
    )

    report = json.loads((tmp_path / "benchmark.json").read_text(encoding="utf-8"))
    assert exit_code == 0
    assert report["arm_statuses"]["legacy"] == "blocked"
    assert report["acceptance"]["status"] == "blocked"
    assert report["final"]["average_metrics"]["verified_autonomous_completion"] == 1.0
