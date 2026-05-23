import json
from pathlib import Path


def test_level1_skeleton_is_metadata_only_and_safe() -> None:
    content = Path("app/atlas/level1_guarded_execution.py").read_text(encoding="utf-8").lower()

    assert "subprocess" not in content
    assert "safe_apply" not in content
    assert "git push" not in content
    assert "git merge" not in content
    assert "os.system" not in content
    assert "shell=true" not in content


def test_scale_94_runtime_and_execution_flags_remain_disabled() -> None:
    manifest = json.loads(Path("web/atlas_ui_surface_manifest.json").read_text(encoding="utf-8"))

    assert manifest["runtime_level"] == "level_0_manual_only"
    assert manifest["level1_execution_enabled"] is False
    assert manifest["autonomous_execution_enabled"] is False


def test_backend_workflow_state_remains_authoritative() -> None:
    text = Path("app/atlas/workflow_state_contract.py").read_text(encoding="utf-8").lower()
    assert '"backend_workflow_state_authoritative": true' in text
