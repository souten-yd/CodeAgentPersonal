"""PI-22 Greenfield build/run/test and real E2E tests.

Acceptance criteria (implementation plan PI-22):
- tests start from normal Atlas API/entrypoint, not synthetic Twin injection;
- build/start/runtime evidence is captured;
- persistence is verified across restart when required;
- unsupported environment is unavailable, not passed.
Required E2E scenarios 1-8 are exercised (run/restart/failure via injected runners).
"""

from __future__ import annotations

from agent.project_intelligence.greenfield_e2e import SCENARIOS, E2EScenario, run_scenario
from agent.project_intelligence.runtime_adapter import (
    FASTAPI_API,
    FASTAPI_PERSISTENCE,
    HTML_JS_CSS,
    PYTHON_CLI,
    SINGLE_HTML,
    VUE_FASTAPI,
    CommandResult,
    ProjectRuntimeAdapter,
    detect_profile,
)


class PassRunner:
    def run(self, command, *, cwd=None):
        return CommandResult(returncode=0, available=True)


class FailRunner:
    def run(self, command, *, cwd=None):
        return CommandResult(returncode=1, available=True)


class UnavailableRunner:
    def run(self, command, *, cwd=None):
        return CommandResult(returncode=127, available=False)


# --- Profile detection covers the scenarios ----------------------------------

def test_profile_detection() -> None:
    assert detect_profile({"index.html": "<html></html>"}) == SINGLE_HTML
    assert detect_profile({"index.html": "x", "a.js": "y", "s.css": "z"}) == HTML_JS_CSS
    assert detect_profile({"app/__main__.py": "print(1)"}) == PYTHON_CLI
    assert detect_profile({"app/main.py": "from fastapi import FastAPI"}) == FASTAPI_API
    assert detect_profile({"app/main.py": "from fastapi import FastAPI\nimport sqlite3"}) == FASTAPI_PERSISTENCE
    assert detect_profile({"app/main.py": "from fastapi import FastAPI", "ui/App.vue": "<template/>"}) == VUE_FASTAPI


# --- Evidence captured from the normal runtime entrypoint --------------------

def test_evidence_captured_from_runtime_entrypoint() -> None:
    scenario = E2EScenario("fastapi", {"app/main.py": "from fastapi import FastAPI\napp=FastAPI()",
                                       "tests/test_x.py": "def test_x():\n    assert True"})
    res = run_scenario(scenario, runner=PassRunner())
    assert res.profile == FASTAPI_API
    # build/test/start evidence, all from the runtime adapter (not synthetic twin injection).
    phases = {e.observation_type for e in res.evidence}
    assert phases == {"runtime_build", "runtime_test", "runtime_start"}
    assert all(e.collector == "runtime_adapter" for e in res.evidence)
    assert res.success is True and res.tests_passed and res.started


# --- All required scenarios succeed with a working runtime -------------------

def test_all_scenarios_succeed_with_working_runtime() -> None:
    for scenario in SCENARIOS:
        res = run_scenario(scenario, runner=PassRunner())
        assert res.success is True, (scenario.name, [d for d in res.diagnostics])


# --- Unsupported environment is unavailable, not passed ----------------------

def test_unsupported_environment_is_unavailable_not_passed() -> None:
    scenario = SCENARIOS[3]  # fastapi_api
    res = run_scenario(scenario, runner=UnavailableRunner())
    assert res.success is False
    results = {e.result for e in res.evidence}
    assert "unavailable" in results
    assert "passed" not in results  # never fabricated


def test_command_allowlist_not_bypassed() -> None:
    # An empty allowlist blocks every command -> unavailable, never passed.
    adapter = ProjectRuntimeAdapter(allowlist=frozenset())
    res = run_scenario(SCENARIOS[3], runner=PassRunner(), adapter=adapter)
    assert res.success is False
    assert all(e.result in ("unavailable", "observed") for e in res.evidence)


# --- Persistence verified across restart -------------------------------------

def test_persistence_verified_across_restart() -> None:
    scenario = next(s for s in SCENARIOS if s.persistence_required)
    ok = run_scenario(scenario, runner=PassRunner(), persistence_checker=PassRunner())
    assert ok.persistence_verified is True and ok.success is True
    # Unavailable persistence environment -> not passed.
    unk = run_scenario(scenario, runner=PassRunner(), persistence_checker=UnavailableRunner())
    assert unk.persistence_verified is None and unk.success is False


# --- Intermediate failure (scenario 8) ---------------------------------------

def test_intermediate_failure_blocks_success_then_recovers() -> None:
    scenario = SCENARIOS[3]
    failed = run_scenario(scenario, runner=FailRunner())
    assert failed.success is False and failed.tests_passed is False
    # Recovery: a subsequent run with a working runner succeeds.
    recovered = run_scenario(scenario, runner=PassRunner())
    assert recovered.success is True
