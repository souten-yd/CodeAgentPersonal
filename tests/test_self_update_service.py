"""Self-update service + /system/self-update endpoint contract.

git_pull is fast-forward only and classifies the common recoverable failures; schedule_restart
spawns the relauncher and arms a self-terminate timer. The endpoint requires acknowledge and
only restarts after a successful pull. None of these tests touch the real git tree or kill the
process — the side-effecting callables are injected/monkeypatched.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.system import _REPO_ROOT
from app.server import create_app
from app.services import self_update


def _runner_returning(mapping):
    """Build a GitRunner that maps the first non-'-C'/path git subcommand to (rc, out, err)."""
    def runner(cmd, cwd, timeout):
        if "rev-parse" in cmd and "--is-inside-work-tree" in cmd:
            return (0, "true\n", "")
        if "pull" in cmd:
            return mapping
        return (0, "", "")
    return runner


def test_git_pull_already_up_to_date():
    res = self_update.git_pull("/repo", runner=_runner_returning((0, "Already up to date.\n", "")))
    assert res["ok"] is True
    assert res["reason"] == "already_up_to_date"
    assert res["changed"] is False


def test_git_pull_updated():
    res = self_update.git_pull("/repo", runner=_runner_returning((0, "Updating a1b2..c3d4\nFast-forward\n", "")))
    assert res["ok"] is True
    assert res["reason"] == "updated"
    assert res["changed"] is True


def test_git_pull_non_fast_forward_is_classified():
    res = self_update.git_pull("/repo", runner=_runner_returning(
        (1, "", "fatal: Not possible to fast-forward, aborting.")))
    assert res["ok"] is False
    assert res["reason"] == "non_fast_forward"


def test_git_pull_dirty_tree_is_classified():
    res = self_update.git_pull("/repo", runner=_runner_returning(
        (1, "", "error: Your local changes to the following files would be overwritten by merge")))
    assert res["ok"] is False
    assert res["reason"] == "dirty_working_tree"


def test_git_pull_rejects_non_repo():
    def runner(cmd, cwd, timeout):
        return (128, "", "fatal: not a git repository")
    res = self_update.git_pull("/tmp/notrepo", runner=runner)
    assert res["ok"] is False
    assert res["reason"] == "not_a_git_repo"


def test_schedule_restart_spawns_and_arms_terminator():
    spawned = {}
    terminated = {"called": False}

    class _FakeChild:
        pid = 4242

    def spawner(host, port, base_dir, parent_pid):
        spawned.update(host=host, port=port, base_dir=base_dir, parent_pid=parent_pid)
        return _FakeChild()

    res = self_update.schedule_restart(
        "0.0.0.0", 8123, "/repo", delay=0.01,
        spawner=spawner, terminator=lambda: terminated.__setitem__("called", True),
    )
    assert res["ok"] is True
    assert res["relauncher_pid"] == 4242
    assert spawned == {"host": "0.0.0.0", "port": 8123, "base_dir": "/repo", "parent_pid": res["parent_pid"]}
    # The timer fires shortly; give it a beat without a fixed sleep loop.
    import time
    for _ in range(50):
        if terminated["called"]:
            break
        time.sleep(0.01)
    assert terminated["called"] is True


def test_self_update_endpoint_requires_acknowledge():
    client = TestClient(create_app())
    resp = client.post("/system/self-update", json={"acknowledge": False})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["reason"] == "acknowledge_required"


def test_self_update_endpoint_pulls_and_schedules_restart(monkeypatch):
    calls = {}

    def fake_pull(base_dir):
        calls["pull_base"] = base_dir
        return {"ok": True, "reason": "updated", "changed": True, "stdout": "", "stderr": ""}

    def fake_restart(host, port, base_dir):
        calls["restart"] = {"host": host, "port": port, "base_dir": base_dir}
        return {"ok": True, "relauncher_pid": 1, "parent_pid": 2}

    monkeypatch.setattr(self_update, "git_pull", fake_pull)
    monkeypatch.setattr(self_update, "schedule_restart", fake_restart)

    client = TestClient(create_app())
    resp = client.post("/system/self-update", json={"acknowledge": True, "restart": True})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["stage"] == "restarting"
    assert calls["pull_base"] == _REPO_ROOT
    assert calls["restart"]["base_dir"] == _REPO_ROOT
    assert calls["restart"]["port"] > 0


def test_self_update_endpoint_pull_failure_does_not_restart(monkeypatch):
    def fake_pull(base_dir):
        return {"ok": False, "reason": "non_fast_forward", "changed": False, "stdout": "", "stderr": "diverged"}

    restarted = {"called": False}

    monkeypatch.setattr(self_update, "git_pull", fake_pull)
    monkeypatch.setattr(self_update, "schedule_restart",
                        lambda *a, **k: restarted.__setitem__("called", True))

    client = TestClient(create_app())
    resp = client.post("/system/self-update", json={"acknowledge": True, "restart": True})
    body = resp.json()
    assert body["ok"] is False
    assert body["stage"] == "pull"
    assert restarted["called"] is False
