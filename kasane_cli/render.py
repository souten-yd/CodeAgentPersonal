from __future__ import annotations

import json
from typing import Any, TextIO


_SECRET_KEY_MARKERS = ("secret", "token", "password", "credential", "api_key", "apikey", "auth")


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            key = str(raw_key)
            if any(marker in key.lower() for marker in _SECRET_KEY_MARKERS):
                clean[key] = "[redacted]"
            else:
                clean[key] = redact(raw_value)
        return clean
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def print_json(payload: dict[str, Any], stdout: TextIO) -> None:
    stdout.write(json.dumps(redact(payload), ensure_ascii=False, indent=2) + "\n")


def render_event(event: dict[str, Any]) -> str:
    seq = event.get("sequence", "")
    kind = event.get("event_type", "")
    status = event.get("status", "")
    item = event.get("item_id", "")
    message = event.get("message", "")
    parts = [f"#{seq}", str(kind)]
    if status:
        parts.append(f"[{status}]")
    if item:
        parts.append(str(item))
    if message:
        parts.append(str(message))
    return " ".join(parts)


def render_status(payload: dict[str, Any]) -> str:
    run_id = payload.get("run_id", "")
    status = payload.get("status", "")
    phase = payload.get("phase", "")
    action = ", ".join(payload.get("next_actions") or [])
    suffix = f" next: {action}" if action else ""
    return f"{run_id} {status}/{phase}{suffix}".strip()
