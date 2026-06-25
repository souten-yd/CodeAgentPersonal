from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any, TextIO

from kasane_cli.client import AtlasRunHttpClient, DEFAULT_BASE_URL
from kasane_cli.render import print_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="KasaneCore Atlas CLI")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--project", default="")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    sub = parser.add_subparsers(dest="command")

    json_parent = argparse.ArgumentParser(add_help=False)
    json_parent.add_argument("--json", action="store_true")

    plan = sub.add_parser("plan", parents=[json_parent], help="Create a PlanPool through the backend API")
    plan.add_argument("--input", required=True)
    plan.add_argument("--project-path", default="")
    plan.add_argument("--workspace-id", default="default")
    plan.add_argument("--sync", action="store_true")

    sub.add_parser("pools-list", parents=[json_parent], help="List PlanPools")
    pools = sub.add_parser("pools", parents=[json_parent], help="List PlanPools")
    pools.set_defaults(command="pools-list")
    pool_show = sub.add_parser("pool-show", parents=[json_parent], help="Show one PlanPool")
    pool_show.add_argument("pool_id")
    pool_alias = sub.add_parser("pool", parents=[json_parent], help="Show one PlanPool")
    pool_alias.add_argument("pool_id")
    pool_alias.set_defaults(command="pool-show")

    start = sub.add_parser("start", parents=[json_parent], help="Create and start a backend run")
    _add_start_args(start)
    run = sub.add_parser("run", parents=[json_parent], help="Create and start a backend run")
    _add_start_args(run)
    run.set_defaults(command="start")

    status = sub.add_parser("status", parents=[json_parent], help="Show run or system status")
    status.add_argument("run_id", nargs="?")

    events = sub.add_parser("events", parents=[json_parent], help="Read run events")
    events.add_argument("run_id")
    events.add_argument("--after-sequence", "--after", type=int, default=0)

    watch = sub.add_parser("watch", parents=[json_parent], help="Watch run events")
    watch.add_argument("run_id")
    watch.add_argument("--after-sequence", "--after", type=int, default=0)
    watch.add_argument("--interval", type=float, default=2.0)
    watch.add_argument("--once", action="store_true")

    decision = sub.add_parser("decision", parents=[json_parent], help="Submit a run decision")
    decision.add_argument("run_id")
    decision.add_argument("--decision", required=True)
    decision.add_argument("--decision-type", default="operator_decision")
    decision.add_argument("--item-id", default="")
    decision.add_argument("--reason", default="")

    approve = sub.add_parser("approve", parents=[json_parent], help="Approve a waiting run")
    approve.add_argument("run_id")
    approve.set_defaults(command="approve")

    cancel = sub.add_parser("cancel", parents=[json_parent], help="Cancel a run")
    cancel.add_argument("run_id")
    cancel.add_argument("--reason", default="operator_cancelled")

    retry = sub.add_parser("retry", parents=[json_parent], help="Request run retry")
    retry.add_argument("run_id")
    retry.add_argument("--reason", default="operator_retry")
    retry.add_argument("--mode", default="", choices=["", "resume", "rerun"])

    revise = sub.add_parser("revise", parents=[json_parent], help="Record a run revision request")
    revise.add_argument("run_id")
    revise.add_argument("--reason", default="revise plan")

    sub.add_parser("interactive", help="Open the interactive Kasane CLI")
    return parser


def _add_start_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--pool-id", required=True)
    parser.add_argument("--item-id", default="")
    parser.add_argument("--item-ids", default="")
    parser.add_argument("--mode", default="fresh", choices=["fresh", "resume", "rerun"])
    parser.add_argument("--workspace-id", default="default")
    parser.add_argument("--preset-id", default="guarded_low_risk")
    parser.add_argument("--command-id", default="")


def run_cli(argv: list[str] | None = None, *, client: Any | None = None, stdout: TextIO | None = None) -> int:
    args = build_parser().parse_args(argv)
    out = stdout or sys.stdout
    http = client or AtlasRunHttpClient(args.base_url)

    if not args.command or args.command == "interactive":
        from kasane_cli.repl import run_repl

        return run_repl(
            http,
            stdout=out,
            base_url=args.base_url,
            project_path=args.project or str(Path.cwd()),
            json_mode=bool(getattr(args, "json", False)),
            quiet=bool(args.quiet),
        )
    return run_command(args, http, out)


def run_command(args: argparse.Namespace, http: Any, out: TextIO) -> int:
    if args.command == "plan":
        query = "?sync=1" if args.sync else ""
        return _emit(
            http.request(
                "POST",
                f"/api/atlas/plan-pools{query}",
                {"input": args.input, "project_path": args.project_path, "workspace_id": args.workspace_id},
            ),
            out,
        )
    if args.command == "pools-list":
        return _emit(http.request("GET", "/api/atlas/plan-pools"), out)
    if args.command == "pool-show":
        return _emit(http.request("GET", f"/api/atlas/plan-pools/{args.pool_id}"), out)
    if args.command == "start":
        return _emit(http.request("POST", "/api/atlas/runs", _start_payload(args)), out)
    if args.command == "status":
        if getattr(args, "run_id", ""):
            return _emit(http.request("GET", f"/api/atlas/runs/{args.run_id}/status"), out)
        return _emit(http.request("GET", "/api/system/status"), out)
    if args.command == "events":
        return _emit(http.request("GET", f"/api/atlas/runs/{args.run_id}/events?after_sequence={args.after_sequence}"), out)
    if args.command == "watch":
        after = args.after_sequence
        while True:
            payload = http.request("GET", f"/api/atlas/runs/{args.run_id}/events?after_sequence={after}")
            print_json(payload, out)
            after = int(payload.get("next_after_sequence") or after)
            if args.once:
                return 0
            status = http.request("GET", f"/api/atlas/runs/{args.run_id}/status")
            if status.get("terminal") is True:
                print_json(status, out)
                return 0
            time.sleep(max(0.1, float(args.interval)))
    if args.command == "decision":
        return _emit(
            http.request(
                "POST",
                f"/api/atlas/runs/{args.run_id}/decisions",
                {
                    "decision": args.decision,
                    "decision_type": args.decision_type,
                    "item_id": args.item_id,
                    "reason": args.reason,
                },
            ),
            out,
        )
    if args.command == "approve":
        return _emit(
            http.request(
                "POST",
                f"/api/atlas/runs/{args.run_id}/decisions",
                {"decision": "approved", "decision_type": "approve", "reason": "cli_approve"},
            ),
            out,
        )
    if args.command == "cancel":
        return _emit(http.request("POST", f"/api/atlas/runs/{args.run_id}/cancel", {"reason": args.reason}), out)
    if args.command == "retry":
        return _emit(http.request("POST", f"/api/atlas/runs/{args.run_id}/retry", {"reason": args.reason, "mode": args.mode}), out)
    if args.command == "revise":
        return _emit(http.request("POST", f"/api/atlas/runs/{args.run_id}/revise", {"reason": args.reason}), out)
    raise SystemExit(f"unknown command: {args.command}")


def _start_payload(args: argparse.Namespace) -> dict[str, Any]:
    item_ids = [item.strip() for item in str(args.item_ids or "").split(",") if item.strip()]
    payload: dict[str, Any] = {
        "pool_id": args.pool_id,
        "workspace_id": args.workspace_id,
        "mode": args.mode,
        "preset_id": args.preset_id,
        "command_id": args.command_id,
        "auto_start": True,
    }
    if args.item_id:
        payload["item_id"] = args.item_id
    if item_ids:
        payload["item_ids"] = item_ids
    return payload


def _emit(payload: dict[str, Any], stdout: TextIO) -> int:
    print_json(payload, stdout)
    return 0


def main() -> int:
    return run_cli()
