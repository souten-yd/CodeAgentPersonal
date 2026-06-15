"""Part A1 — durable Anti-Pattern memory store."""
from __future__ import annotations

from agent.twin_control_plane.anti_pattern_memory import (
    AntiPatternEntry, AntiPatternMemoryStore, AntiPatternSource,
)


def _entry(pattern_id="p1", occ=1, conf=0.8):
    return AntiPatternEntry(pattern_id=pattern_id, title="t", description="d",
                            source=AntiPatternSource.PROOF_LEDGER, confidence=conf,
                            occurrences=occ, evidence_refs=["e1"], categories=["test_weakening"])


def test_persists_and_reloads(tmp_path):
    store = AntiPatternMemoryStore(tmp_path / "apm")
    store.record(_entry())
    reloaded = AntiPatternMemoryStore(tmp_path / "apm").load()
    assert len(reloaded.entries) == 1
    assert reloaded.entries[0].pattern_id == "p1"


def test_same_pattern_merges_occurrences(tmp_path):
    store = AntiPatternMemoryStore(tmp_path / "apm")
    store.record(_entry(occ=1))
    mem = store.record(_entry(occ=1))  # same pattern_id -> merge, not duplicate
    assert len(mem.entries) == 1
    assert mem.entries[0].occurrences == 2


def test_distinct_patterns_accumulate(tmp_path):
    store = AntiPatternMemoryStore(tmp_path / "apm")
    store.record(_entry("p1"))
    store.record(_entry("p2"))
    assert {e.pattern_id for e in store.load().entries} == {"p1", "p2"}


def test_missing_memory_loads_empty(tmp_path):
    mem = AntiPatternMemoryStore(tmp_path / "apm").load()
    assert mem.entries == []
