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
    html = workspace / "index.html"
    text = html.read_text(encoding="utf-8") if html.is_file() else ""
    report["independent_acceptance"] = {
        "status": "passed" if acceptance_text in text else "failed",
        "path": str(html),
        "acceptance_text": acceptance_text,
    }


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
    task = corpus["tasks"][0]
    task_id = str(task["task_id"])
    acceptance_text = str(task["acceptance_text"])
    reports_dir = output_json.parent / "pir15_live_benchmark_reports"

    arms = {
        "legacy": {},
        "final": {ENV_ENABLED: "1"},
    }
    arm_reports: dict[str, dict[str, Any]] = {}
    for arm, rollout_env in arms.items():
        workspace = workspace_root / arm / task_id
        report = run_live_greenfield(
            workspace,
            data_root / arm,
            arm_name=arm,
            rollout_env=rollout_env,
        )
        _annotate_independent_acceptance(report, workspace, acceptance_text)
        arm_reports[arm] = report
        _write_json(reports_dir / f"{arm}_{task_id}.json", report)

    comparative = write_artifact_comparative_report(
        corpus_path,
        output_json,
        legacy_reports={task_id: arm_reports["legacy"]},
        final_reports={task_id: arm_reports["final"]},
        generated_at=str(arm_reports["final"].get("finished_at") or arm_reports["legacy"].get("finished_at") or ""),
    )
    comparative["arm_statuses"] = {
        "legacy": arm_reports["legacy"].get("status"),
        "final": arm_reports["final"].get("status"),
    }
    comparative["arm_report_paths"] = {
        "legacy": str(reports_dir / f"legacy_{task_id}.json"),
        "final": str(reports_dir / f"final_{task_id}.json"),
    }
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
