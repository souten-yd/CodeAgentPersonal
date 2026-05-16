"""FastAPI application factory skeleton.

This module is a deliberately small step toward moving application construction
out of ``main.py``.  The current production entrypoint remains ``main:app``;
``/workspace`` and ``/static`` mounting helpers now live here alongside
the optional ``/ui`` and ``/assets`` static mounts.  Only low-dependency
health/system routers have moved so far; other route registration, lifespan
handling, and middleware still live in ``main.py`` until later, focused
refactors can move one concern at a time.
"""

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles


Lifespan = Callable[[FastAPI], AbstractAsyncContextManager[None] | AsyncIterator[None]]


def create_app(
    *,
    lifespan: Lifespan | None = None,
    web_dir: str | Path | None = None,
    ui_dir: str | Path | None = None,
    assets_dir: str | Path | None = None,
    workspace_dir: str | Path | None = None,
) -> FastAPI:
    """Create a FastAPI app shell for the future app-factory migration.

    The returned app intentionally does not mirror ``main.app`` yet.  Keeping
    this factory minimal lets us add contract tests and a stable destination for
    later extraction work without changing ``uvicorn main:app`` behavior.
    """
    app = FastAPI(lifespan=lifespan)

    configure_middleware(app)
    include_routers(app)
    configure_workspace_mount(app, workspace_dir=workspace_dir)
    configure_static_assets(
        app,
        ui_dir=ui_dir,
        assets_dir=assets_dir,
        web_dir=web_dir,
    )

    return app


def configure_workspace_mount(
    app: FastAPI,
    *,
    workspace_dir: str | Path | None = None,
) -> None:
    """Mount the optional workspace directory served by ``main.py``.

    The workspace mount is intentionally separate from UI/static asset mounts
    because it exposes user/project files rather than bundled application
    assets. Missing directories are ignored so factory-based tests and callers
    can opt in only when a workspace root exists.
    """
    if workspace_dir and Path(workspace_dir).is_dir():
        app.mount(
            "/workspace",
            StaticFiles(directory=str(workspace_dir), html=True),
            name="workspace",
        )


def configure_static_assets(
    app: FastAPI,
    *,
    web_dir: str | Path | None = None,
    ui_dir: str | Path | None = None,
    assets_dir: str | Path | None = None,
) -> None:
    """Mount optional UI, asset, and web static directories.

    Passing directories lets callers opt in to the same static asset mounts used
    by ``main.py`` while keeping the app-factory shell lightweight by default.
    Missing directories are ignored so local/test setups can provide only the
    static roots they need.
    """
    if ui_dir and Path(ui_dir).is_dir():
        app.mount("/ui", StaticFiles(directory=str(ui_dir), html=True), name="ui")
    if assets_dir and Path(assets_dir).is_dir():
        app.mount(
            "/assets", StaticFiles(directory=str(assets_dir), html=False), name="assets"
        )
    if web_dir and Path(web_dir).is_dir():
        app.mount("/static", StaticFiles(directory=str(web_dir)), name="static")


def include_routers(app: FastAPI) -> None:
    """Register API routers that have been split out of ``main.py``.

    Router modules are imported lazily inside this function so importing
    ``app.server`` remains a side-effect-free factory operation.  This keeps
    production ``main:app`` startup order explicit and prevents future router
    splits from accidentally probing CUDA, ASR/TTS, LLM, filesystem-heavy, or
    network-backed runtime state during module import.
    """
    from app.api.atlas_pipeline import router as atlas_pipeline_router
    from app.api.audio import router as audio_router
    from app.api.echo import router as echo_router
    from app.api.jobs import router as jobs_router
    from app.api.lumen import router as lumen_router
    from app.api.model_settings import router as model_settings_router
    from app.api.nexus import router as nexus_router
    from app.api.projects import router as projects_router
    from app.api.runtime_controls import router as runtime_controls_router
    from app.api.settings import router as settings_router
    from app.api.system import router as system_router
    from app.api.system_status import router as system_status_router

    app.include_router(atlas_pipeline_router)
    app.include_router(audio_router)
    app.include_router(echo_router)
    app.include_router(jobs_router)
    app.include_router(lumen_router)
    app.include_router(system_router)
    app.include_router(system_status_router)
    # Settings owns /settings*, including static defaults aliases that must be
    # registered before the /settings/{key} dynamic route inside the router.
    app.include_router(settings_router)
    app.include_router(model_settings_router)
    app.include_router(runtime_controls_router)
    app.include_router(projects_router)
    app.include_router(nexus_router)


def configure_middleware(app: FastAPI) -> None:
    """Placeholder for future middleware registration.

    Middleware configuration remains in ``main.py`` until a dedicated follow-up
    can move it without changing the public app import path.
    """
    return None
