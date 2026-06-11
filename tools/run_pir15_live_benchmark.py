from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent.project_intelligence.live_benchmark import (
    load_benchmark_corpus,
    write_artifact_comparative_report,
)
from agent.project_intelligence.rollout import ENV_ENABLED
from tools.run_pir13_live_greenfield import run_live_greenfield


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _annotate_independent_acceptance(report: dict[str, Any], workspace: Path, acceptance_text: str) -> None:
    acceptance_path = Path(str(report.get("acceptance_path") or "index.html"))
    target = workspace / acceptance_path
    text = target.read_text(encoding="utf-8") if target.is_file() else ""
    report["independent_acceptance"] = {
        "status": "passed" if acceptance_text in text else "failed",
        "path": str(target),
        "acceptance_text": acceptance_text,
    }


def _seed_workspace(workspace: Path, seed: str) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    if seed == "empty":
        return
    if seed == "existing_html_app":
        (workspace / "index.html").write_text(
            "<!doctype html><html><body><h1>Atlas Existing Baseline</h1><p>Status: pending</p></body></html>\n",
            encoding="utf-8",
        )
        (workspace / "app.py").write_text(
            "def status_label():\n    return 'existing-baseline'\n",
            encoding="utf-8",
        )
        tests_dir = workspace / "tests"
        tests_dir.mkdir(exist_ok=True)
        (tests_dir / "test_app.py").write_text(
            "from app import status_label\n\n\ndef test_status_label_is_string():\n    assert isinstance(status_label(), str)\n",
            encoding="utf-8",
        )
        return
    raise ValueError(f"unsupported PIR-15 workspace seed: {seed}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the PIR-15 live comparative benchmark.")
    parser.add_argument(
        "--corpus",
        type=Path,
        default=REPO_ROOT / "docs" / "generated" / "atlas_project_intelligence_pir15_benchmark_corpus.json",
    )
    parser.add_argument("--workspace-root", type=Path, default=None)
    parser.add_argument("--data-root", type=Path, default=None)
    parser.add_argument("--output-json", type=Path, default=REPO_ROOT / "ca_data" / "atlas" / "pir15_live_benchmark_report.json")
    parser.add_argument(
        "--allow-blocked-exit-zero",
        action="store_true",
        help="Exit 0 when a live arm is blocked. The report remains blocked, not passed.",
    )
    return parser.parse_args(argv)


def run_live_comparative_benchmark(
    *,
    corpus_path: Path,
    workspace_root: Path,
    data_root: Path,
    output_json: Path,
) -> dict[str, Any]:
    corpus = load_benchmark_corpus(corpus_path)
    reports_dir = output_json.parent / "pir15_live_benchmark_reports"

    arms = {
        "legacy": {},
        "final": {ENV_ENABLED: "1"},
    }
    arm_reports: dict[str, dict[str, list[dict[str, Any]]]] = {arm: {} for arm in arms}
    arm_report_paths: dict[str, dict[str, list[str]]] = {arm: {} for arm in arms}
    for arm, rollout_env in arms.items():
        for task in corpus["tasks"]:
            task_id = str(task["task_id"])
            repetitions = int(task.get("repetitions", 1))
            arm_reports[arm][task_id] = []
            arm_report_paths[arm][task_id] = []
            for repetition in range(1, repetitions + 1):
                run_id = f"{task_id}_r{repetition}"
                workspace = workspace_root / arm / run_id
                _seed_workspace(workspace, str(task["workspace_seed"]))
                report = run_live_greenfield(
                    workspace,
                    data_root / arm / run_id,
                    arm_name=arm,
                    rollout_env=rollout_env,
                    goal=str(task["requirement"]),
                    required_text=str(task["acceptance_text"]),
                    acceptance_path=str(task.get("acceptance_path") or "index.html"),
                    expected_target_files=[str(path) for path in task.get("expected_target_files", ["index.html"])],
                    project_name=f"pir15-{task_id}",
                    workspace_id=f"pir15-{arm}-{run_id}",
                    automation_features={"clarification_mode": "auto"},
                )
                report["benchmark_task_id"] = task_id
                report["benchmark_repetition"] = repetition
                report["workspace_seed"] = str(task["workspace_seed"])
                _annotate_independent_acceptance(report, workspace, str(task["acceptance_text"]))
                arm_reports[arm][task_id].append(report)
                report_path = reports_dir / f"{arm}_{run_id}.json"
                arm_report_paths[arm][task_id].append(str(report_path))
                _write_json(report_path, report)

    comparative = write_artifact_comparative_report(
        corpus_path,
        output_json,
        legacy_reports={task_id: arm_reports["legacy"][task_id] for task_id in arm_reports["legacy"]},
        final_reports={task_id: arm_reports["final"][task_id] for task_id in arm_reports["final"]},
        generated_at=str(
            next(
                (
                    report.get("finished_at")
                    for reports_by_task in arm_reports["final"].values()
                    for report in reversed(reports_by_task)
                    if report.get("finished_at")
                ),
                "",
            )
        ),
    )
    comparative["arm_statuses"] = {
        arm: "passed"
        if all(report.get("status") == "passed" for reports in arm_reports[arm].values() for report in reports)
        else "blocked"
        for arm in arms
    }
    comparative["arm_report_paths"] = arm_report_paths
    _write_json(output_json, comparative)
    return comparative


def main_cli(argv: list[str]) -> int:
    args = parse_args(argv)
    temp_root: tempfile.TemporaryDirectory[str] | None = None
    if args.workspace_root is None:
        temp_root = tempfile.TemporaryDirectory(prefix="pir15-live-benchmark-")
        workspace_root = Path(temp_root.name) / "workspaces"
        data_root = Path(temp_root.name) / "atlas_data"
    else:
        workspace_root = args.workspace_root
        data_root = args.data_root or args.workspace_root.parent / "atlas_data"
    try:
        report = run_live_comparative_benchmark(
            corpus_path=args.corpus,
            workspace_root=workspace_root,
            data_root=data_root,
            output_json=args.output_json,
        )
        print(
            json.dumps(
                {
                    "status": "passed" if all(value == "passed" for value in report["arm_statuses"].values()) else "blocked",
                    "report": str(args.output_json),
                    "arm_statuses": report["arm_statuses"],
                    "verdict": report["comparison"]["verdict"],
                },
                ensure_ascii=False,
            )
        )
        if all(value == "passed" for value in report["arm_statuses"].values()):
            return 0
        return 0 if args.allow_blocked_exit_zero else 2
    finally:
        if temp_root is not None:
            temp_root.cleanup()


if __name__ == "__main__":
    raise SystemExit(main_cli(sys.argv[1:]))
