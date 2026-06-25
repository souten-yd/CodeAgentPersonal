from __future__ import annotations

from collections.abc import Mapping

from app.startup_banner import BANNER_TEXT, should_show_cli_banner


def should_show_banner(
    *,
    json_mode: bool = False,
    quiet: bool = False,
    env: Mapping[str, str] | None = None,
) -> bool:
    return should_show_cli_banner(json_mode=json_mode, quiet=quiet, env=env)
