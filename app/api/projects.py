"""Project read-only API router.

This router owns the low-risk project listing/history/file endpoints that have
been split from ``main.py``. Provider lookups keep production ``main.app`` on
its existing filesystem/database-backed behavior, while provider-less
``create_app()`` returns conservative lightweight fallbacks without scanning the
workspace or touching jobs/LLM runtime state.
"""

from collections.abc import Callable
from copy import deepcopy
from typing import Any

from fastapi import APIRouter, Request

router = APIRouter()

ProjectsListProvider = Callable[[], Any]
ProjectHistoryProvider = Callable[[str], Any]
ProjectFilesProvider = Callable[[str], Any]

PROJECTS_DEFAULT_PAYLOAD: dict[str, Any] = {"projects": []}
PROJECT_HISTORY_DEFAULT_PAYLOAD: dict[str, Any] = {"sessions": []}
PROJECT_FILES_DEFAULT_PAYLOAD: dict[str, Any] = {"project": "", "files": []}


def default_projects_payload() -> dict[str, Any]:
    """Return a conservative project list without scanning the workspace."""
    return deepcopy(PROJECTS_DEFAULT_PAYLOAD)


def default_project_history_payload() -> dict[str, Any]:
    """Return an empty history payload without opening project storage."""
    return deepcopy(PROJECT_HISTORY_DEFAULT_PAYLOAD)


def default_project_files_payload(project: str) -> dict[str, Any]:
    """Return an empty file list without reading the project filesystem."""
    payload = deepcopy(PROJECT_FILES_DEFAULT_PAYLOAD)
    payload["project"] = project
    return payload


def get_projects_list_provider(request: Request) -> ProjectsListProvider | None:
    """Look up the optional app-state provider for the project list."""
    provider = getattr(request.app.state, "projects_list_provider", None)
    if callable(provider):
        return provider
    return None


def get_project_history_provider(request: Request) -> ProjectHistoryProvider | None:
    """Look up the optional app-state provider for project history."""
    provider = getattr(request.app.state, "project_history_provider", None)
    if callable(provider):
        return provider
    return None


def get_project_files_provider(request: Request) -> ProjectFilesProvider | None:
    """Look up the optional app-state provider for project files."""
    provider = getattr(request.app.state, "project_files_provider", None)
    if callable(provider):
        return provider
    return None


@router.get("/projects")
def get_projects_api(request: Request) -> Any:
    provider = get_projects_list_provider(request)
    if provider is not None:
        return provider()
    return default_projects_payload()


@router.get("/projects/{project}/history")
def get_project_history_api(project: str, request: Request) -> Any:
    provider = get_project_history_provider(request)
    if provider is not None:
        return provider(project)
    return default_project_history_payload()


@router.get("/projects/{project}/files")
def get_project_files_api(project: str, request: Request) -> Any:
    provider = get_project_files_provider(request)
    if provider is not None:
        return provider(project)
    return default_project_files_payload(project)
