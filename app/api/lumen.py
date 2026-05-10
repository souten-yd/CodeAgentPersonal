"""Lumen API router.

This router owns Lumen HTTP validation and response shaping. Runtime
orchestration and direct tool execution live in ``app.services.lumen_runtime``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.lumen.budgets import LumenNewsBudget, LumenSearchBudget, LumenWeatherBudget
from app.services.lumen_runtime import (
    LUMEN_MAX_STEPS_DEFAULT,
    build_lumen_tool_status,
    run_lumen_news_direct,
    run_lumen_weather_direct,
    validate_lumen_submit_request,
)

router = APIRouter()


class LumenSubmitRequest(BaseModel):
    """Request body accepted by POST /lumen/submit for chat-only Lumen jobs."""

    message: str
    project: str = "default"
    mode: str = "chat"
    max_steps: int = LUMEN_MAX_STEPS_DEFAULT
    search_enabled: bool | None = None
    tool_policy: str = "auto"
    search_policy: str = "auto"
    search_budget: LumenSearchBudget = Field(default_factory=LumenSearchBudget)
    weather_budget: LumenWeatherBudget = Field(default_factory=LumenWeatherBudget)
    news_budget: LumenNewsBudget = Field(default_factory=LumenNewsBudget)
    location: str | None = None
    llm_url: str = ""
    chat_history: list[Any] = Field(default_factory=list)


class LumenWeatherToolRequest(BaseModel):
    location: str | None = None
    message: str = ""
    weather_budget: LumenWeatherBudget = Field(default_factory=LumenWeatherBudget)


class LumenNewsToolRequest(BaseModel):
    message: str = ""
    topic: str | None = None
    news_budget: LumenNewsBudget = Field(default_factory=LumenNewsBudget)


def _job_submit_provider(request: Request):
    provider = getattr(request.app.state, "job_submit_provider", None)
    if callable(provider):
        return provider
    return None


@router.post("/lumen/submit")
def submit_lumen_api(req: LumenSubmitRequest, request: Request) -> Any:
    """Primary Lumen chat submit endpoint."""
    try:
        validate_lumen_submit_request(req)
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)

    provider = _job_submit_provider(request)
    if provider is not None:
        return provider(req)
    return {
        "ok": False,
        "status": "unavailable",
        "job_id": None,
        "message": "lumen submit provider unavailable",
    }


@router.get("/lumen/tools/status")
def get_lumen_tools_status_api() -> dict[str, Any]:
    return build_lumen_tool_status()


@router.post("/lumen/tools/weather")
def post_lumen_weather_tool_api(req: LumenWeatherToolRequest) -> dict[str, Any]:
    return run_lumen_weather_direct(req)


@router.post("/lumen/tools/news")
def post_lumen_news_tool_api(req: LumenNewsToolRequest) -> dict[str, Any]:
    return run_lumen_news_direct(req)
