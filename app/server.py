"""FastAPI application factory skeleton.

This module is the first, deliberately small step toward moving application
construction out of ``main.py``.  The current production entrypoint remains
``main:app``; route registration, lifespan handling, middleware, and static
asset mounts still live in ``main.py`` until later, focused refactors can move
one concern at a time.
"""

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

Lifespan = Callable[[FastAPI], AbstractAsyncContextManager[None] | AsyncIterator[None]]


def create_app(
    *, lifespan: Lifespan | None = None, web_dir: str | Path | None = None
) -> FastAPI:
    """Create a FastAPI app shell for the future app-factory migration.

    The returned app intentionally does not mirror ``main.app`` yet.  Keeping
    this factory minimal lets us add contract tests and a stable destination for
    later extraction work without changing ``uvicorn main:app`` behavior.
    """
    app = FastAPI(lifespan=lifespan)

    configure_middleware(app)
    include_routers(app)
    configure_static_assets(app, web_dir=web_dir)

    return app


def configure_static_assets(
    app: FastAPI, *, web_dir: str | Path | None = None
) -> None:
    """Mount optional web static assets under ``/static``.

    Passing ``web_dir`` lets callers opt in to the same static asset mount used
    by ``main.py`` while keeping the app-factory shell lightweight by default.
    """
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
