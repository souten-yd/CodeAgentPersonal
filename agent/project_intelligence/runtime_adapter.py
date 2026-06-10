"""Project runtime adapter (PI-22).

A coarse runtime adapter that detects a project's runtime profile and provides safe build,
test, and startup commands under the existing command authority (an allowlist + an injected
command runner). It never bypasses the command allowlist, and an unsupported environment
(missing tool / non-allowlisted command) is reported as ``unavailable`` — never ``passed``
(ADR-PI-013). Real processes are run by the injected runner, so the adapter itself is pure.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from agent.project_intelligence.contracts import RuntimeObservationRecord

# Runtime profiles.
SINGLE_HTML = "single_html"
HTML_JS_CSS = "html_js_css"
PYTHON_CLI = "python_cli"
FASTAPI_API = "fastapi_api"
FASTAPI_PERSISTENCE = "fastapi_persistence"
VUE_FASTAPI = "vue_fastapi"
UNKNOWN = "unknown"

# Commands whose first token is allowlisted under existing command authority.
DEFAULT_COMMAND_ALLOWLIST = frozenset({
    "pip", "python", "pytest", "uvicorn", "npm", "npx", "node", "playwright", "open",
})


@dataclass
class CommandResult:
    returncode: int
    stdout: str = ""
    available: bool = True   # False == tool/environment unavailable


class CommandRunner(Protocol):
    def run(self, command: list[str], *, cwd: str | None = None) -> CommandResult: ...


def _now() -> datetime:
    return datetime.now(timezone.utc)


def detect_profile(files: dict[str, str]) -> str:
    exts = {("." + f.rsplit(".", 1)[-1]).lower() for f in files if "." in f}
    has_py = ".py" in exts
    has_html = ".html" in exts
    has_vue = ".vue" in exts
    has_js_css = bool({".js", ".css", ".jsx", ".ts"} & exts)
    py_content = "\n".join(c for f, c in files.items() if f.endswith(".py"))
    has_fastapi = "fastapi" in py_content.lower()
    has_db = any(k in py_content.lower() for k in ("sqlite3", "sqlalchemy", "database", "psycopg", " execute("))

    if has_vue and has_fastapi:
        return VUE_FASTAPI
    if has_fastapi and has_db:
        return FASTAPI_PERSISTENCE
    if has_fastapi:
        return FASTAPI_API
    if has_py:
        return PYTHON_CLI
    if has_html and has_js_css:
        return HTML_JS_CSS
    if has_html:
        return SINGLE_HTML
    return UNKNOWN


_PROFILE_COMMANDS: dict[str, dict[str, list[str]]] = {
    SINGLE_HTML: {"build": [], "test": ["playwright", "test"], "start": ["open", "index.html"]},
    HTML_JS_CSS: {"build": ["npm", "run", "build"], "test": ["playwright", "test"], "start": ["open", "index.html"]},
    PYTHON_CLI: {"build": ["pip", "install", "-e", "."], "test": ["pytest", "-q"], "start": ["python", "-m", "app"]},
    FASTAPI_API: {"build": ["pip", "install", "-e", "."], "test": ["pytest", "-q"], "start": ["uvicorn", "app.main:app"]},
    FASTAPI_PERSISTENCE: {"build": ["pip", "install", "-e", "."], "test": ["pytest", "-q"], "start": ["uvicorn", "app.main:app"]},
    VUE_FASTAPI: {"build": ["npm", "install"], "test": ["pytest", "-q"], "start": ["uvicorn", "app.main:app"]},
}


class ProjectRuntimeAdapter:
    def __init__(self, *, allowlist: frozenset[str] = DEFAULT_COMMAND_ALLOWLIST) -> None:
        self._allowlist = allowlist

    def commands_for(self, profile: str) -> dict[str, list[str]]:
        return _PROFILE_COMMANDS.get(profile, {"build": [], "test": [], "start": []})

    def _observe(self, *, project_id: str, workspace_id: str, phase: str, command: list[str],
                 runner: CommandRunner, source_revision: str | None) -> RuntimeObservationRecord:
        oid = f"rt-{phase}:{uuid.uuid4().hex[:10]}"
        if not command:
            return self._record(oid, project_id, workspace_id, phase, "observed",
                                f"no {phase} command for profile", source_revision)
        if command[0] not in self._allowlist:
            # Never bypass the command allowlist; a blocked command is unavailable, not passed.
            return self._record(oid, project_id, workspace_id, phase, "unavailable",
                                f"command {command[0]!r} not in allowlist", source_revision)
        result = runner.run(command)
        if not result.available:
            return self._record(oid, project_id, workspace_id, phase, "unavailable",
                                f"environment unavailable for {' '.join(command)}", source_revision)
        if phase == "start":
            outcome = "observed" if result.returncode == 0 else "failed"
        else:
            outcome = "passed" if result.returncode == 0 else "failed"
        return self._record(oid, project_id, workspace_id, phase, outcome,
                            f"{' '.join(command)} -> rc={result.returncode}", source_revision)

    @staticmethod
    def _record(oid, project_id, workspace_id, phase, result, summary, source_revision) -> RuntimeObservationRecord:
        return RuntimeObservationRecord(
            observation_id=oid, project_id=project_id, workspace_id=workspace_id,
            collector="runtime_adapter", collector_version="1", observation_type=f"runtime_{phase}",
            subject_refs=[f"runtime://{phase}"], source_revision=source_revision, timestamp=_now(),
            result=result, summary=summary,
        )

    def build(self, profile, *, runner, project_id, workspace_id, source_revision=None) -> RuntimeObservationRecord:
        return self._observe(project_id=project_id, workspace_id=workspace_id, phase="build",
                             command=self.commands_for(profile)["build"], runner=runner,
                             source_revision=source_revision)

    def test(self, profile, *, runner, project_id, workspace_id, source_revision=None) -> RuntimeObservationRecord:
        return self._observe(project_id=project_id, workspace_id=workspace_id, phase="test",
                             command=self.commands_for(profile)["test"], runner=runner,
                             source_revision=source_revision)

    def start(self, profile, *, runner, project_id, workspace_id, source_revision=None) -> RuntimeObservationRecord:
        return self._observe(project_id=project_id, workspace_id=workspace_id, phase="start",
                             command=self.commands_for(profile)["start"], runner=runner,
                             source_revision=source_revision)
