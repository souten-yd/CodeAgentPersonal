from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent.project_intelligence.retirement_gate import (
    write_active_rollout_transition_evidence,
    write_pir15_retirement_gate,
)
from agent.project_intelligence.data_migration_evidence import write_pir15_data_migration_evidence


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build PIR-15 rollout and legacy-retirement gate evidence.")
    parser.add_argument(
        "--benchmark-report",
        type=Path,
        default=REPO_ROOT / "ca_data" / "atlas" / "pir15_live_benchmark_report.r12.json",
    )
    parser.add_argument(
        "--consumer-registry",
        type=Path,
        default=REPO_ROOT / "ca_data" / "atlas" / "pir14_consumer_registry.current.json",
    )
    parser.add_argument(
        "--rollout-evidence",
        type=Path,
        default=REPO_ROOT / "ca_data" / "atlas" / "pir14_rollout_evidence.current.json",
    )
    parser.add_argument(
        "--consumer-cutover-gate",
        type=Path,
        default=REPO_ROOT / "ca_data" / "atlas" / "pir14_consumer_cutover_gate.current.json",
    )
    parser.add_argument(
        "--active-rollout-output",
        type=Path,
        default=REPO_ROOT / "ca_data" / "atlas" / "pir15_active_rollout_transition.current.json",
    )
    parser.add_argument(
        "--ca-data-dir",
        type=Path,
        default=REPO_ROOT / "ca_data" / "atlas" / "pir15_active_rollout_data",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=REPO_ROOT / "ca_data" / "atlas" / "pir15_retirement_gate.current.json",
    )
    parser.add_argument(
        "--data-migration-evidence",
        type=Path,
        default=REPO_ROOT / "ca_data" / "atlas" / "pir15_data_migration_evidence.current.json",
    )
    parser.add_argument("--data-migration-verified", action="store_true")
    parser.add_argument("--docs-updated", action="store_true")
    parser.add_argument(
        "--allow-blocked-exit-zero",
        action="store_true",
        help="Exit 0 when the retirement gate is blocked. The report remains blocked, not passed.",
    )
    return parser.parse_args(argv)


def main_cli(argv: list[str]) -> int:
    args = parse_args(argv)
    write_active_rollout_transition_evidence(args.ca_data_dir, args.active_rollout_output)
    data_migration_evidence = write_pir15_data_migration_evidence(
        args.data_migration_evidence,
        benchmark_report_path=args.benchmark_report,
        consumer_registry_path=args.consumer_registry,
        rollout_evidence_path=args.rollout_evidence,
        consumer_cutover_gate_path=args.consumer_cutover_gate,
        active_rollout_evidence_path=args.active_rollout_output,
    )
    report = write_pir15_retirement_gate(
        args.output_json,
        benchmark_report_path=args.benchmark_report,
        consumer_registry_path=args.consumer_registry,
        rollout_evidence_path=args.rollout_evidence,
        consumer_cutover_gate_path=args.consumer_cutover_gate,
        active_rollout_evidence_path=args.active_rollout_output,
        data_migration_verified=args.data_migration_verified,
        data_migration_evidence_path=args.data_migration_evidence,
        docs_updated=args.docs_updated,
    )
    print(
        json.dumps(
            {
                "status": report["status"],
                "report": str(args.output_json),
                "active_rollout": report["summary"]["active_rollout_passed"],
                "legacy_consumer_count": report["summary"]["legacy_consumer_count"],
                "data_migration_evidence": data_migration_evidence["status"],
                "blocked_reasons": report["summary"]["blocked_reasons"],
            },
            ensure_ascii=False,
        )
    )
    if report["status"] == "passed":
        return 0
    return 0 if args.allow_blocked_exit_zero else 2


if __name__ == "__main__":
    raise SystemExit(main_cli(sys.argv[1:]))
