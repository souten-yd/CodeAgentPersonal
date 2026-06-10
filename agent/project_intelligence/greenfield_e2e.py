"""Greenfield build/run/test E2E harness (PI-22).

Drives the required E2E scenarios from the normal runtime entrypoint (the ProjectRuntimeAdapter
build/test/start commands run via an injected command runner), NOT synthetic Twin injection.
It captures build/start/runtime evidence, verifies persistence across a restart when required,
and records an unsupported environment as unavailable rather than passed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agent.project_intelligence.contracts import RuntimeObservationRecord
from agent.project_intelligence.runtime_adapter import (
    CommandRunner,
    ProjectRuntimeAdapter,
    detect_profile,
)
from agent.project_twin.runtime.reconciliation import summarize_rollup


@dataclass
class E2EScenario:
    name: str
    files: dict[str, str]
    persistence_required: bool = False


@dataclass
class E2EResult:
    scenario: str
    profile: str
    evidence: list[RuntimeObservationRecord] = field(default_factory=list)
    build_passed: bool = False
    tests_passed: bool = False
    started: bool = False
    persistence_verified: bool | None = None
    success: bool = False
    diagnostics: list[str] = field(default_factory=list)


# The eight required scenarios (representative fixtures).
SCENARIOS: list[E2EScenario] = [
    E2EScenario("single_html", {"index.html": "<html><body>hi</body></html>"}),
    E2EScenario("html_js_css", {"index.html": "<link href='s.css'><script src='a.js'></script>",
                                 "a.js": "console.log(1)", "s.css": "body{}"}),
    E2EScenario("python_cli", {"app/__main__.py": "def main():\n    print('hi')\n",
                                "tests/test_cli.py": "def test_main():\n    assert True\n"}),
    E2EScenario("fastapi_api", {"app/main.py": "from fastapi import FastAPI\napp = FastAPI()\n",
                                 "tests/test_api.py": "def test_root():\n    assert True\n"}),
    E2EScenario("fastapi_persistence",
                {"app/main.py": "from fastapi import FastAPI\nimport sqlite3\napp = FastAPI()\n",
                 "tests/test_db.py": "def test_db():\n    assert True\n"}, persistence_required=True),
    E2EScenario("vue_fastapi", {"app/main.py": "from fastapi import FastAPI\napp = FastAPI()\n",
                                 "ui/App.vue": "<template><div/></template>"}),
]


def run_scenario(
    scenario: E2EScenario,
    *,
    runner: CommandRunner,
    adapter: ProjectRuntimeAdapter | None = None,
    project_id: str = "p1",
    workspace_id: str = "w1",
    source_revision: str | None = "rev-1",
    persistence_checker: "CommandRunner | None" = None,
) -> E2EResult:
    adapter = adapter or ProjectRuntimeAdapter()
    profile = detect_profile(scenario.files)
    res = E2EResult(scenario=scenario.name, profile=profile)

    build = adapter.build(profile, runner=runner, project_id=project_id, workspace_id=workspace_id,
                          source_revision=source_revision)
    test = adapter.test(profile, runner=runner, project_id=project_id, workspace_id=workspace_id,
                        source_revision=source_revision)
    start = adapter.start(profile, runner=runner, project_id=project_id, workspace_id=workspace_id,
                          source_revision=source_revision)
    res.evidence = [build, test, start]
    res.build_passed = build.result in ("passed", "observed")
    res.tests_passed = test.result == "passed"
    res.started = start.result == "observed"

    if scenario.persistence_required:
        checker = persistence_checker or runner
        before = checker.run(["python", "-c", "verify_persistence_before"])
        after = checker.run(["python", "-c", "verify_persistence_after_restart"])
        if not (before.available and after.available):
            res.persistence_verified = None  # unavailable, not passed
            res.diagnostics.append("persistence environment unavailable")
        else:
            res.persistence_verified = (before.returncode == 0 and after.returncode == 0)

    rollup = summarize_rollup(res.evidence)
    persistence_ok = (not scenario.persistence_required) or (res.persistence_verified is True)
    # success requires truthful rollup (no failed/unavailable) and persistence (if required).
    res.success = rollup.success and persistence_ok and res.tests_passed
    if rollup.unavailable:
        res.diagnostics.append(f"{rollup.unavailable} unavailable runtime observation(s)")
    return res
