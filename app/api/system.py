"""System status API router."""

import os
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.env_detection import detect_gpu_profile, detect_os_profile, detect_runpod

router = APIRouter()

# Repo root (…/KasaneCore): app/api/system.py -> app/api -> app -> repo root.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SYSTEM_READINESS_DEFAULT_PAYLOAD: dict[str, Any] = {
    "fastapi": "ready",
    "model_db_exists": False,
    "model_db_status_available": False,
    "model_db_status": {},
    "llm_autoload_eligible": False,
    "autoload_reason": "unknown",
    "llm_running": False,
}



def default_system_readiness_payload() -> dict[str, Any]:
    """Return the stable readiness response shape without app-specific probes."""
    return dict(SYSTEM_READINESS_DEFAULT_PAYLOAD)



@router.get("/system/readiness")
def system_readiness(request: Request) -> dict[str, Any]:
    provider = getattr(request.app.state, "system_readiness_provider", None)
    if callable(provider):
        return provider()
    return default_system_readiness_payload()



@router.get("/system/env")
def system_env() -> dict[str, Any]:
    """Runtime environment probe (must not raise HTTP 500)."""
    style_bert_vits2_device = os.environ.get("CODEAGENT_STYLE_BERT_VITS2_DEVICE", "")
    try:
        return {
            "runpod": detect_runpod(),
            "os": detect_os_profile(),
            "gpu": detect_gpu_profile(),
            "style_bert_vits2_device": style_bert_vits2_device,
        }
    except Exception as e:
        return {
            "error": "failed_to_detect_environment",
            "detail": str(e),
            "runpod": False,
            "os": {},
            "gpu": {},
            "style_bert_vits2_device": style_bert_vits2_device,
        }


class SelfUpdateRequest(BaseModel):
    acknowledge: bool = False
    restart: bool = True


def _resolve_restart_port(request: Request) -> int:
    """Pick the port the new server should bind to. Prefer the port this request came in on,
    then an explicit env override, then the conventional default."""
    port = request.url.port
    if port:
        return int(port)
    env_port = os.environ.get("CODEAGENT_PORT") or os.environ.get("PORT")
    try:
        return int(env_port) if env_port else 8000
    except ValueError:
        return 8000


@router.post("/system/self-update")
def system_self_update(request: Request, body: SelfUpdateRequest) -> dict[str, Any]:
    """Pull the latest KasaneCore code and (optionally) relaunch the FastAPI server.

    Requires ``acknowledge=true`` because a restart briefly drops the running server. The pull
    is fast-forward only and never destroys local changes; the restart is scheduled out-of-band
    so this response can return first.
    """
    from app.services import self_update

    if not body.acknowledge:
        return {"ok": False, "stage": "acknowledge", "reason": "acknowledge_required",
                "message": "更新は確認が必要です（acknowledge=true）。"}

    pull = self_update.git_pull(_REPO_ROOT)
    result: dict[str, Any] = {"ok": bool(pull.get("ok")), "stage": "pull", "pull": pull}
    if not pull.get("ok"):
        return result

    if body.restart:
        host = os.environ.get("CODEAGENT_HOST", "0.0.0.0")
        port = _resolve_restart_port(request)
        try:
            restart = self_update.schedule_restart(host, port, _REPO_ROOT)
            result["stage"] = "restarting"
            result["restart"] = restart
            result["message"] = "更新を取得しました。サーバを再起動します…"
        except Exception as exc:  # noqa: BLE001 — surface, never 500 the operator's update.
            result["stage"] = "pulled_no_restart"
            result["restart"] = {"ok": False, "error": str(exc)}
            result["message"] = "更新は取得しましたが再起動の開始に失敗しました。手動で再起動してください。"
    else:
        result["stage"] = "pulled"
        result["message"] = ("最新の状態です。" if pull.get("reason") == "already_up_to_date"
                             else "更新を取得しました（再起動は未実施）。")
    return result
