"""FastAPI application factory skeleton.

This module is a deliberately small step toward moving application construction
out of ``main.py``.  The current production entrypoint remains ``main:app``;
static asset mounts are centralized in this module, while route registration,
lifespan handling, and middleware still live in ``main.py`` until later, focused
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
) -> FastAPI:
    """Create a FastAPI app shell for the future app-factory migration.

    The returned app intentionally does not mirror ``main.app`` yet.  Keeping
    this factory minimal lets us add contract tests and a stable destination for
    later extraction work without changing ``uvicorn main:app`` behavior.
    """
    app = FastAPI(lifespan=lifespan)

    configure_middleware(app)
    include_routers(app)
    configure_static_assets(
        app,
        ui_dir=ui_dir,
        assets_dir=assets_dir,
        web_dir=web_dir,
    )

    return app


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
    """Placeholder for future API router registration.

    Router splitting is intentionally out of scope for this preparatory change;
    existing route decorators and router includes remain in ``main.py``.
    """
    return None


def configure_middleware(app: FastAPI) -> None:
    """Placeholder for future middleware registration.

    Middleware configuration remains in ``main.py`` until a dedicated follow-up
    can move it without changing the public app import path.
    """
    return None
