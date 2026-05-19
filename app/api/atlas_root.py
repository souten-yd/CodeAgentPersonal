from __future__ import annotations

import os
from pathlib import Path

from fastapi import Request


def resolve_atlas_ca_data_root(request: Request | None = None) -> Path:
    if request is not None:
        for attr in ("atlas_ca_data_root", "atlas_ca_data_dir", "ca_data_root"):
            state_value = getattr(request.app.state, attr, "")
            if state_value:
                return Path(str(state_value)).expanduser().resolve()
    env_value = os.environ.get("CODEAGENT_CA_DATA_DIR") or os.environ.get("CA_DATA")
    if env_value:
        return Path(env_value).expanduser().resolve()
    codeagent_data_dir = os.environ.get("CODEAGENT_DATA_DIR", "").strip()
    if codeagent_data_dir:
        return (Path(codeagent_data_dir).expanduser().resolve() / "ca_data").resolve()
    return Path("ca_data").resolve()
