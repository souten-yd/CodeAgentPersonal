from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from typing import TextIO


BANNER_TEXT = r""" _  __                         ____               
| |/ /__ _ ___  __ _ _ __   ___/ ___|___  _ __ ___ 
| ' // _` / __|/ _` | '_ \ / _ \ |   / _ \| '__/ _ \
| . \ (_| \__ \ (_| | | | |  __/ |__| (_) | | |  __/
|_|\_\__,_|___/\__,_|_| |_|\___|\____\___/|_|  \___|

        Atlas * Portal * Forge * Twin"""


def should_show_cli_banner(
    *,
    json_mode: bool = False,
    quiet: bool = False,
    env: Mapping[str, str] | None = None,
) -> bool:
    values = env or os.environ
    if json_mode or quiet:
        return False
    if _banner_disabled(values):
        return False
    return True


def should_show_server_banner(
    *,
    env: Mapping[str, str] | None = None,
    stream: TextIO | None = None,
    is_pytest: bool | None = None,
) -> bool:
    values = env or os.environ
    if _banner_disabled(values):
        return False
    if _machine_readable_mode(values):
        return False
    under_pytest = is_pytest if is_pytest is not None else _running_under_pytest(values)
    if under_pytest:
        return False
    if _env_truthy(values.get("KASANE_BANNER")):
        return True
    target = stream or sys.stdout
    return bool(getattr(target, "isatty", lambda: False)())


def print_server_startup_banner_once(
    *,
    env: Mapping[str, str] | None = None,
    stream: TextIO | None = None,
    is_pytest: bool | None = None,
) -> bool:
    target = stream or sys.stdout
    if not should_show_server_banner(env=env, stream=target, is_pytest=is_pytest):
        return False
    target.write(BANNER_TEXT + "\n")
    target.write("KasaneCore server startup\n")
    target.flush()
    return True


def _banner_disabled(env: Mapping[str, str]) -> bool:
    if _env_truthy(env.get("KASANE_NO_BANNER")):
        return True
    value = env.get("KASANE_BANNER")
    return value is not None and value.strip().lower() in {"0", "false", "no", "off"}


def _machine_readable_mode(env: Mapping[str, str]) -> bool:
    for key in (
        "KASANE_JSON",
        "KASANE_JSON_MODE",
        "KASANE_MACHINE_READABLE",
        "CODEAGENT_JSON",
        "CODEAGENT_MACHINE_READABLE",
    ):
        if _env_truthy(env.get(key)):
            return True
    for key in ("KASANE_LOG_FORMAT", "CODEAGENT_LOG_FORMAT", "LOG_FORMAT"):
        if str(env.get(key, "")).strip().lower() == "json":
            return True
    return False


def _running_under_pytest(env: Mapping[str, str]) -> bool:
    return bool(env.get("PYTEST_CURRENT_TEST")) or "pytest" in sys.modules


def _env_truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}
