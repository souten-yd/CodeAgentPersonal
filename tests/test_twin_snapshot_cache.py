"""HEAD-snapshot cache for the Project Twin store.

Materializing the full graph dominates assess_impact at repo scale (~95 s for 417k nodes in
KasaneCore) and a single triage loads it several times. The store caches the HEAD snapshot keyed by
head revision; these tests prove it reuses within a revision and invalidates when the head advances.
"""
from __future__ import annotations

from agent.project_twin.module import DigitalTwinModuleImpl
from agent.project_twin.facade import ProjectIdentity, RefreshTwinRequest


def _build(tmp_path, body: str):
    project = tmp_path / "proj"
    project.mkdir(exist_ok=True)
    (project / "mod.py").write_text(body, encoding="utf-8")
    mod = DigitalTwinModuleImpl(db_path=str(tmp_path / "twin.sqlite"))
    mod.refresh(RefreshTwinRequest(
        project=ProjectIdentity(project_id="p", workspace_id="default", project_path=str(project)),
        full_rebuild=True))
    return mod


def test_head_snapshot_is_cached_within_a_revision(tmp_path):
    mod = _build(tmp_path, "def a():\n    return 1\n")
    store = mod._store
    pid = "p\x1fdefault"
    s1 = store.get_snapshot(pid)
    s2 = store.get_snapshot(pid)
    assert s1 is s2  # same object reused — no re-deserialization


def test_cache_invalidates_when_head_advances(tmp_path):
    mod = _build(tmp_path, "def a():\n    return 1\n")
    store = mod._store
    pid = "p\x1fdefault"
    s1 = store.get_snapshot(pid)
    # A refresh that changes the source advances the head -> the cache must not return the old snapshot.
    (tmp_path / "proj" / "mod.py").write_text("def a():\n    return 1\n\ndef b():\n    return a()\n", encoding="utf-8")
    mod.refresh(RefreshTwinRequest(
        project=ProjectIdentity(project_id="p", workspace_id="default", project_path=str(tmp_path / "proj")),
        full_rebuild=True))
    s3 = store.get_snapshot(pid)
    assert s3 is not s1
    assert s3.twin_revision_id != s1.twin_revision_id
    # The new symbol is present in the fresh snapshot.
    assert any(n.canonical_ref.endswith("#b") for n in s3.nodes)
