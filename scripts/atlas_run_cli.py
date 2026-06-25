from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any, TextIO


DEFAULT_BASE_URL = "http://127.0.0.1:8000"


class AtlasRunHttpClient:
    def __init__(self, base_url: str = DEFAULT_BASE_URL, *, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base_url + path, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                text = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise SystemExit(f"HTTP {exc.code}: {detail}") from exc
        return json.loads(text) if text.strip() else {}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Thin Atlas Run API client")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    sub = parser.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan", help="Create a PlanPool through the backend API")
    plan.add_argument("--input", required=True)
    plan.add_argument("--project-path", default="")
    plan.add_argument("--workspace-id", default="default")
    plan.add_argument("--sync", action="store_true")

    sub.add_parser("pools-list", help="List PlanPools")
    pool_show = sub.add_parser("pool-show", help="Show one PlanPool")
    pool_show.add_argument("pool_id")

    start = sub.add_parser("start", help="Create and start a backend run")
    start.add_argument("--pool-id", required=True)
    start.add_argument("--item-id", default="")
    start.add_argument("--item-ids", default="")
    start.add_argument("--mode", default="fresh", choices=["fresh", "resume", "rerun"])
    start.add_argument("--workspace-id", default="default")
    start.add_argument("--preset-id", default="guarded_low_risk")
    start.add_argument("--command-id", default="")

    status = sub.add_parser("status", help="Show run status")
    status.add_argument("run_id")

    watch = sub.add_parser("watch", help="Watch run events")
    watch.add_argument("run_id")
    watch.add_argument("--after-sequence", type=int, default=0)
    watch.add_argument("--interval", type=float, default=2.0)
    watch.add_argument("--once", action="store_true")

    decision = sub.add_parser("decision", help="Submit a run decision")
    decision.add_argument("run_id")
    decision.add_argument("--decision", required=True)
    decision.add_argument("--decision-type", default="operator_decision")
    decision.add_argument("--item-id", default="")
    decision.add_argument("--reason", default="")

    cancel = sub.add_parser("cancel", help="Cancel a run")
    cancel.add_argument("run_id")
    cancel.add_argument("--reason", default="operator_cancelled")

    retry = sub.add_parser("retry", help="Request run retry")
    retry.add_argument("run_id")
    retry.add_argument("--reason", default="operator_retry")

    return parser


def _print_json(payload: dict[str, Any], stdout: TextIO) -> None:
    stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def run_cli(argv: list[str] | None = None, *, client: Any | None = None, stdout: TextIO | None = None) -> int:
    args = build_parser().parse_args(argv)
    out = stdout or sys.stdout
    http = client or AtlasRunHttpClient(args.base_url)

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
        item_ids = [item.strip() for item in str(args.item_ids or "").split(",") if item.strip()]
        return _emit(
            http.request(
                "POST",
                "/api/atlas/runs",
                {
                    "pool_id": args.pool_id,
                    "workspace_id": args.workspace_id,
                    "item_id": args.item_id,
                    "item_ids": item_ids,
                    "mode": args.mode,
                    "preset_id": args.preset_id,
                    "command_id": args.command_id,
                    "auto_start": True,
                },
            ),
            out,
        )
    if args.command == "status":
        return _emit(http.request("GET", f"/api/atlas/runs/{args.run_id}/status"), out)
    if args.command == "watch":
        after = args.after_sequence
        while True:
            payload = http.request("GET", f"/api/atlas/runs/{args.run_id}/events?after_sequence={after}")
            _print_json(payload, out)
            after = int(payload.get("next_after_sequence") or after)
            if args.once:
                return 0
            status = http.request("GET", f"/api/atlas/runs/{args.run_id}/status")
            if status.get("terminal") is True:
                _print_json(status, out)
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
    if args.command == "cancel":
        return _emit(http.request("POST", f"/api/atlas/runs/{args.run_id}/cancel", {"reason": args.reason}), out)
    if args.command == "retry":
        return _emit(http.request("POST", f"/api/atlas/runs/{args.run_id}/retry", {"reason": args.reason}), out)
    raise SystemExit(f"unknown command: {args.command}")


def _emit(payload: dict[str, Any], stdout: TextIO) -> int:
    _print_json(payload, stdout)
    return 0


def main() -> int:
    return run_cli()


if __name__ == "__main__":
    raise SystemExit(main())
