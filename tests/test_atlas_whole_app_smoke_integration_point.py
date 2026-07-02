"""The whole-app browser smoke must actually RUN at the integration point (the last app-touching
item), not be deferred forever. Otherwise runtime cross-file errors — e.g. a renderer calling an
ENGINE method the engine never exported — are never caught and a broken app ships as "completed".
"""
from __future__ import annotations

from types import SimpleNamespace

from agent.atlas_auto_verification_service import AtlasAutoVerificationService


def _item(item_id, targets, *, status="queued", scope=None, group_role=None):
    meta = {}
    if scope is not None:
        meta["verification_scope"] = scope
    if group_role is not None:
        meta["group_role"] = group_role
    return SimpleNamespace(item_id=item_id, target_files=targets, status=status, metadata=meta)


def _svc():
    return AtlasAutoVerificationService.__new__(AtlasAutoVerificationService)


def test_last_app_touching_item_runs_smoke():
    svc = _svc()
    game = _item("s3", ["js/game.js"])
    pool = SimpleNamespace(items=[_item("s1", ["index.html"], status="completed"),
                                  _item("s2", ["js/engine.js"], status="completed"),
                                  game], completed_item_ids=["s1", "s2"])
    assert svc._defer_whole_app_smoke(game, pool) is False  # integration point -> run


def test_defers_while_a_later_app_item_remains():
    svc = _svc()
    engine = _item("s2", ["js/engine.js"])
    pool = SimpleNamespace(items=[_item("s1", ["index.html"], status="completed"),
                                  engine,
                                  _item("s3", ["js/game.js"], status="queued")],
                           completed_item_ids=["s1"])
    assert svc._defer_whole_app_smoke(engine, pool) is True  # a later app file remains -> defer


def test_explicit_scope_wins():
    svc = _svc()
    it = _item("x", ["js/game.js"], scope="integration")
    pool = SimpleNamespace(items=[it, _item("y", ["js/more.js"])], completed_item_ids=[])
    assert svc._defer_whole_app_smoke(it, pool) is False  # explicit integration -> run
    it2 = _item("x", ["js/game.js"], scope="deferred_smoke")
    assert svc._defer_whole_app_smoke(it2, pool) is True


def test_non_app_file_not_deferred():
    svc = _svc()
    it = _item("x", ["src/util.py"])
    pool = SimpleNamespace(items=[it, _item("y", ["js/app.js"])], completed_item_ids=[])
    assert svc._defer_whole_app_smoke(it, pool) is False  # no app runtime file -> nothing to defer
