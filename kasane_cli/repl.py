from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any, Callable, TextIO

from kasane_cli.banner import BANNER_TEXT, should_show_banner
from kasane_cli.render import print_json, render_event, render_status


InputFn = Callable[[str], str]


HELP_TEXT = """/help
/status [run_id]
/project [path]
/model
/plan <goal>
/pools
/pool <pool_id>
/run <pool_id>
/watch [run_id]
/events [run_id] [--after N]
/approve <run_id>
/decision <run_id> <decision>
/retry <run_id>
/revise <run_id> <note>
/cancel <run_id>
/exit"""


def run_repl(
    client: Any,
    *,
    stdout: TextIO,
    base_url: str,
    project_path: str,
    json_mode: bool = False,
    quiet: bool = False,
    input_fn: InputFn | None = None,
) -> int:
    state = {"project_path": str(Path(project_path).resolve()), "active_pool_id": "", "active_run_id": ""}
    if should_show_banner(json_mode=json_mode, quiet=quiet):
        stdout.write(BANNER_TEXT + "\n")
        stdout.write("KasaneCore Atlas CLI\n")
        stdout.write(f"project: {state['project_path']}\n")
        stdout.write(f"server:  {base_url}\n")
        stdout.write(f"model:   {_model_label(client)}\n\n")
        stdout.write("Type /help for commands. Type natural language to create or continue an Atlas plan.\n")
    input_impl = input_fn or input
    while True:
        prompt = f"kasane[{state['active_run_id']}]> " if state["active_run_id"] else "kasane> "
        try:
            line = input_impl(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            stdout.write("\n")
            return 0
        if not line:
            continue
        if line in {"/exit", "/quit"}:
            return 0
        if line.startswith("/"):
            if _handle_slash(line, client, stdout, state) == "exit":
                return 0
            continue
        payload = client.request(
            "POST",
            "/api/atlas/plan-pools?sync=1",
            {"input": line, "project_path": state["project_path"], "workspace_id": "default"},
        )
        _remember_pool(payload, state)
        print_json(payload, stdout)


def _handle_slash(line: str, client: Any, stdout: TextIO, state: dict[str, str]) -> str:
    parts = shlex.split(line)
    command = parts[0][1:] if parts else ""
    args = parts[1:]
    if command == "help":
        stdout.write(HELP_TEXT + "\n")
        return ""
    if command == "project":
        if args:
            state["project_path"] = str(Path(args[0]).resolve())
        stdout.write(state["project_path"] + "\n")
        return ""
    if command == "model":
        stdout.write(_model_label(client) + "\n")
        return ""
    if command == "status":
        run_id = args[0] if args else state.get("active_run_id", "")
        payload = client.request("GET", f"/api/atlas/runs/{run_id}/status") if run_id else client.request("GET", "/api/system/status")
        stdout.write(render_status(payload) + "\n" if run_id else "")
        if not run_id:
            print_json(payload, stdout)
        return ""
    if command == "plan":
        goal = " ".join(args).strip()
        if not goal:
            stdout.write("usage: /plan <goal>\n")
            return ""
        payload = client.request(
            "POST",
            "/api/atlas/plan-pools?sync=1",
            {"input": goal, "project_path": state["project_path"], "workspace_id": "default"},
        )
        _remember_pool(payload, state)
        print_json(payload, stdout)
        return ""
    if command == "pools":
        print_json(client.request("GET", "/api/atlas/plan-pools"), stdout)
        return ""
    if command == "pool":
        pool_id = args[0] if args else state.get("active_pool_id", "")
        print_json(client.request("GET", f"/api/atlas/plan-pools/{pool_id}"), stdout)
        return ""
    if command == "run":
        pool_id = args[0] if args else state.get("active_pool_id", "")
        payload = client.request("POST", "/api/atlas/runs", {"pool_id": pool_id, "mode": "fresh", "auto_start": True})
        state["active_run_id"] = str(payload.get("run_id") or "")
        print_json(payload, stdout)
        return ""
    if command in {"watch", "events"}:
        run_id = args[0] if args else state.get("active_run_id", "")
        after = _after_arg(args)
        payload = client.request("GET", f"/api/atlas/runs/{run_id}/events?after_sequence={after}")
        for event in payload.get("events") or []:
            stdout.write(render_event(event) + "\n")
        return ""
    if command == "approve":
        run_id = args[0] if args else state.get("active_run_id", "")
        print_json(client.request("POST", f"/api/atlas/runs/{run_id}/decisions", {"decision": "approved", "decision_type": "approve"}), stdout)
        return ""
    if command == "decision":
        if len(args) < 2:
            stdout.write("usage: /decision <run_id> <decision>\n")
            return ""
        print_json(client.request("POST", f"/api/atlas/runs/{args[0]}/decisions", {"decision": args[1], "decision_type": "operator_decision"}), stdout)
        return ""
    if command == "retry":
        run_id = args[0] if args else state.get("active_run_id", "")
        print_json(client.request("POST", f"/api/atlas/runs/{run_id}/retry", {"reason": "cli_retry", "mode": "resume"}), stdout)
        return ""
    if command == "revise":
        run_id = args[0] if args else state.get("active_run_id", "")
        note = " ".join(args[1:]).strip() or "revise plan"
        print_json(client.request("POST", f"/api/atlas/runs/{run_id}/revise", {"reason": note}), stdout)
        return ""
    if command == "cancel":
        run_id = args[0] if args else state.get("active_run_id", "")
        print_json(client.request("POST", f"/api/atlas/runs/{run_id}/cancel", {"reason": "cli_cancel"}), stdout)
        return ""
    if command in {"clear", "open"}:
        stdout.write("\n")
        return ""
    stdout.write("unknown command. Type /help.\n")
    return ""


def _model_label(client: Any) -> str:
    try:
        payload = client.request("GET", "/api/system/status")
    except Exception:  # noqa: BLE001
        return "unavailable"
    model = payload.get("model") or payload.get("model_id") or payload.get("active_model") or ""
    return str(model or "unavailable")


def _remember_pool(payload: dict[str, Any], state: dict[str, str]) -> None:
    pool_id = payload.get("pool_id") or (payload.get("plan_pool") or {}).get("pool_id")
    if pool_id:
        state["active_pool_id"] = str(pool_id)


def _after_arg(args: list[str]) -> int:
    if "--after" in args:
        idx = args.index("--after")
        if idx + 1 < len(args):
            return int(args[idx + 1])
    return 0
