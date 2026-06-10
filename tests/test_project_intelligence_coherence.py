"""PI-21 coherent multi-file generation and consistency validation tests.

Acceptance criteria (implementation plan PI-21):
- mismatches become typed Convergence gaps;
- local repair is attempted before Blueprint revision;
- missing dependency and missing file have separate recovery policies;
- no generated placeholder counts as completion.
"""

from __future__ import annotations

from agent.architecture_blueprint.generator import BlueprintSpec, FileSpec, generate_blueprint
from agent.project_intelligence.coherence import (
    ADD_DEPENDENCY,
    API_MISMATCH,
    ASSET_MISSING,
    BLUEPRINT_REVISION,
    CREATE_MISSING_FILE,
    DEPENDENCY_MISSING,
    IMPORTS_UNRESOLVED,
    LOCAL_REPAIR,
    PATH_NOT_IN_MANIFEST,
    PLACEHOLDER_NOT_COMPLETE,
    check_coherence,
    to_convergence_gaps,
)


def _blueprint(paths):
    spec = BlueprintSpec(
        requirements=["R1"],
        files=[FileSpec(path=p, requirement_ids=["R1"], acceptance=["x"]) for p in paths],
        entrypoint="app/main.py", build_command="b", start_command="s", test_command="t",
    )
    return generate_blueprint(project_id="p1", workspace_id="w1", spec=spec, project_mode="empty")


def _codes(report):
    return {g.code for g in report.gaps}


# --- Coherent slice ----------------------------------------------------------

def test_coherent_slice_has_no_gaps() -> None:
    bp = _blueprint(["app/models.py", "app/service.py"])
    files = {
        "app/__init__.py": "",
        "app/models.py": "class User:\n    def __init__(self):\n        self.id = 1\n",
        "app/service.py": "from app.models import User\n\ndef make():\n    return User()\n",
    }
    report = check_coherence(revision=bp, generated_files=files)
    assert report.coherent is True, _codes(report)


# --- Imports: missing local file vs missing dependency (separate policies) ----

def test_missing_local_import_is_create_missing_file() -> None:
    bp = _blueprint(["app/service.py"])
    files = {"app/service.py": "from app.models import User\n\ndef f():\n    return User()\n"}
    report = check_coherence(revision=bp, generated_files=files)
    gap = next(g for g in report.gaps if g.code == IMPORTS_UNRESOLVED)
    assert gap.recovery_policy == CREATE_MISSING_FILE


def test_missing_dependency_is_add_dependency() -> None:
    bp = _blueprint(["app/service.py"])
    files = {"app/service.py": "import requests\n\ndef f():\n    return requests.get('/')\n"}
    report = check_coherence(revision=bp, generated_files=files, dependencies=set())
    gap = next(g for g in report.gaps if g.code == DEPENDENCY_MISSING)
    assert gap.recovery_policy == ADD_DEPENDENCY
    # declaring the dependency resolves it.
    ok = check_coherence(revision=bp, generated_files=files, dependencies={"requests"})
    assert DEPENDENCY_MISSING not in _codes(ok)


# --- Assets + API agreement --------------------------------------------------

def test_missing_asset_detected() -> None:
    bp = _blueprint(["index.html"])
    files = {"index.html": "<link href='style.css'><script src='app.js'></script>"}
    report = check_coherence(revision=bp, generated_files=files)
    assert ASSET_MISSING in _codes(report)


def test_api_mismatch_detected() -> None:
    bp = _blueprint(["api.py", "ui.js"])
    files = {
        "api.py": "from fastapi import APIRouter\nrouter = APIRouter()\n@router.get('/users')\ndef u():\n    return []\n",
        "ui.js": "fetch('/customers').then(r => r.json())\n",  # no matching backend route
    }
    report = check_coherence(revision=bp, generated_files=files)
    assert API_MISMATCH in _codes(report)


# --- Manifest membership + unexpected classification -------------------------

def test_path_not_in_manifest_is_classified_and_blueprint_revision() -> None:
    bp = _blueprint(["app/models.py"])
    files = {"app/models.py": "class A:\n    pass\n", "rogue/extra.py": "def x():\n    return 1\n"}
    report = check_coherence(revision=bp, generated_files=files)
    assert "rogue/extra.py" in report.unexpected_files
    gap = next(g for g in report.gaps if g.code == PATH_NOT_IN_MANIFEST)
    assert gap.recovery_policy == BLUEPRINT_REVISION


# --- Placeholder is not completion -------------------------------------------

def test_placeholder_is_not_completion() -> None:
    bp = _blueprint(["app/models.py"])
    files = {"app/models.py": "# TODO: implement\npass\n"}
    report = check_coherence(revision=bp, generated_files=files)
    assert PLACEHOLDER_NOT_COMPLETE in _codes(report)
    assert "app/models.py" in report.placeholder_files


# --- Local repair preferred before Blueprint revision ------------------------

def test_local_repair_preferred_before_blueprint_revision() -> None:
    bp = _blueprint(["app/models.py"])
    files = {
        "app/models.py": "# TODO\npass\n",        # placeholder -> local_repair
        "rogue.py": "def x():\n    return 1\n",     # not in manifest -> blueprint_revision
    }
    report = check_coherence(revision=bp, generated_files=files)
    assert report.recommended_first_action() == LOCAL_REPAIR  # local repair first


# --- Mismatches become typed Convergence gaps --------------------------------

def test_mismatches_become_convergence_gaps() -> None:
    bp = _blueprint(["app/service.py"])
    files = {"app/service.py": "from app.models import User\n"}
    report = check_coherence(revision=bp, generated_files=files)
    conv = to_convergence_gaps(report)
    assert conv and all(g.mandatory for g in conv)
    assert any("imports_unresolved" in g.description for g in conv)
