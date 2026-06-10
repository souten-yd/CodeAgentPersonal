"""PI-23 existing capability consolidation and consumer cutover tests.

Acceptance criteria (implementation plan PI-23):
- new consumers use facade only;
- parity exceptions are documented;
- rollback is tested;
- forbidden direct dependencies are zero for migrated consumers.
Plus: compatibility adapters first; cutover order; no deletion before parity.
"""

from __future__ import annotations

import pytest

from agent.project_intelligence.consolidation import (
    CUTOVER_ORDER,
    FACADE,
    LEGACY,
    CompatibilityAdapter,
    Consumer,
    ConsumerRegistry,
    CutoverError,
    retirement_ready,
    shadow_compare,
)


# --- Compatibility adapter first ---------------------------------------------

def test_compatibility_adapter_adds_provenance() -> None:
    adapter = CompatibilityAdapter(
        capability="impact_map", legacy_version="v1",
        translate=lambda legacy: {"impacted": legacy["files"]},
    )
    out = adapter.adapt({"files": ["a.py", "b.py"]})
    assert out["impacted"] == ["a.py", "b.py"]
    assert out["_provenance"]["source"] == "legacy_adapter"
    assert out["_provenance"]["legacy_version"] == "v1"


# --- Shadow comparison + documented exceptions -------------------------------

def test_shadow_compare_parity_and_documented_exception() -> None:
    legacy = {"impacted": ["a.py"], "confidence": 0.5}
    new = {"impacted": ["a.py"], "confidence": 0.9}  # confidence differs
    report = shadow_compare("impact_map", legacy, new)
    assert ("confidence", 0.5, 0.9) in report.mismatched
    assert report.parity is False  # undocumented mismatch -> not parity
    # Document the known difference -> parity holds.
    report2 = shadow_compare("impact_map", legacy, new, documented_exceptions=("confidence",))
    assert report2.parity is True


def test_identical_results_are_parity() -> None:
    r = shadow_compare("planning_context", {"x": 1}, {"x": 1, "_provenance": {"a": 1}})
    assert r.parity is True and "x" in r.matched


# --- Cutover order enforced --------------------------------------------------

def test_cutover_order_enforced() -> None:
    reg = ConsumerRegistry()
    reg.register(Consumer("insp1", "inspection_api"))
    reg.register(Consumer("gen1", "generation_context"))
    # generation_context cannot cut over before inspection_api migrates.
    with pytest.raises(CutoverError):
        reg.migrate("gen1")
    reg.migrate("insp1")  # inspection first
    assert reg.can_cutover("planning_context") is True


def test_new_consumers_use_facade_only() -> None:
    reg = ConsumerRegistry()
    reg.register(Consumer("insp1", "inspection_api"))
    reg.migrate("insp1")
    assert reg.consumers("inspection_api")[0].mode == FACADE
    assert reg.all_facade("inspection_api") is True


# --- Forbidden direct deps zero for migrated consumers -----------------------

def test_forbidden_dependency_blocks_cutover() -> None:
    reg = ConsumerRegistry()
    reg.register(Consumer("insp1", "inspection_api", forbidden_imports_clear=False))
    with pytest.raises(CutoverError):
        reg.migrate("insp1")  # still imports legacy directly
    # clear the dependency, then migrate.
    reg.consumers("inspection_api")[0].forbidden_imports_clear = True
    reg.migrate("insp1")
    assert reg.migrated_consumers_have_no_forbidden_deps() is True


# --- Rollback is tested ------------------------------------------------------

def test_rollback_reverts_to_legacy() -> None:
    reg = ConsumerRegistry()
    reg.register(Consumer("insp1", "inspection_api"))
    reg.migrate("insp1")
    assert reg.consumers("inspection_api")[0].mode == FACADE
    reg.rollback("insp1")
    assert reg.consumers("inspection_api")[0].mode == LEGACY


# --- No deletion before parity (retirement gate) -----------------------------

def test_retirement_blocked_until_all_gates_pass() -> None:
    reg = ConsumerRegistry()
    reg.register(Consumer("insp1", "inspection_api"))
    parity = shadow_compare("inspection_api", {"x": 1}, {"x": 2})  # mismatch

    # legacy consumer remains + no parity + no rollback test + tests not passing.
    ready, reasons = retirement_ready("inspection_api", reg, parity, rollback_tested=False, tests_pass=False)
    assert ready is False and len(reasons) >= 3

    # migrate consumer, establish parity, test rollback, pass tests.
    reg.migrate("insp1")
    good = shadow_compare("inspection_api", {"x": 1}, {"x": 1})
    ready2, reasons2 = retirement_ready("inspection_api", reg, good, rollback_tested=True, tests_pass=True)
    assert ready2 is True and reasons2 == []


def test_documented_superiority_satisfies_parity_gate() -> None:
    reg = ConsumerRegistry()  # no consumers for this capability -> zero legacy
    parity = shadow_compare("impact_map", {"x": 1}, {"x": 2})
    ready, _ = retirement_ready("impact_map", reg, parity, rollback_tested=True, tests_pass=True,
                                documented_superiority=True)
    assert ready is True


def test_cutover_order_is_the_specified_sequence() -> None:
    assert CUTOVER_ORDER[0] == "inspection_api"
    assert CUTOVER_ORDER[-1] == "final_rollup"
    assert CUTOVER_ORDER.index("planning_context") < CUTOVER_ORDER.index("generation_context")
