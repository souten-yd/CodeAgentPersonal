from __future__ import annotations

import os


BANNER_TEXT = r""" _  __                         ____               
| |/ /__ _ ___  __ _ _ __   ___/ ___|___  _ __ ___ 
| ' // _` / __|/ _` | '_ \ / _ \ |   / _ \| '__/ _ \
| . \ (_| \__ \ (_| | | | |  __/ |__| (_) | | |  __/
|_|\_\__,_|___/\__,_|_| |_|\___|\____\___/|_|  \___|

        Atlas * Portal * Forge * Twin"""


def should_show_banner(*, json_mode: bool = False, quiet: bool = False) -> bool:
    if json_mode or quiet:
        return False
    if os.environ.get("KASANE_NO_BANNER") == "1":
        return False
    if os.environ.get("KASANE_BANNER") == "0":
        return False
    return True
