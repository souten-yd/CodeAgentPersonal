import json
from pathlib import Path

from agent.model_forge.preset_runner import LocalForgePresetRunner, PresetRunnerTask
from agent.model_forge.route_matrix import ChangeClass
from agent.model_forge.stage_taxonomy import ForgeStage


class _Resp:
    status = 200

    def __init__(self, body: dict) -> None:
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def read(self) -> bytes:
        return json.dumps(self._body).encode("utf-8")


def test_local_preset_runner_uses_provider_registry_and_evaluator(monkeypatch) -> None:
    def _fake_urlopen(request, timeout=0):
        url = request.full_url if hasattr(request, "full_url") else str(request)
        if url.endswith("/v1/models"):
            return _Resp({"data": [{"id": "m"}]})
        assert url.endswith("/v1/chat/completions")
        return _Resp({
            "model": "m",
            "choices": [{"message": {"content": "def add(a, b):\n    return a + b\n"}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 7},
        })

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    runner = LocalForgePresetRunner(base_url="http://local", model_id="m")

    assert runner.probe() is True
    result = runner.run(PresetRunnerTask(
        preset_id="quick_standard",
        stage=ForgeStage.PATCH_GENERATION,
        change_class=ChangeClass.MICRO,
        task_category="quick",
        system_prompt="system",
        user_prompt="user",
        output_contract="text",
        requirement_coverage_ratio=1.0,
    ))

    assert result.runner_path == "ProviderRegistry/LocalOpenAICompatibleProvider/RouteSelector/CandidateEvaluator"
    assert result.provider_id == "local_openai_compatible"
    assert result.model_id == "m"
    assert result.execution_result.contract_valid is True
    assert "def add" in result.raw_output
    assert result.evaluation.verdict == "eligible"
    evidence = result.evidence_payload(package="PFH-6")
    assert evidence["runner_path"] == result.runner_path
    assert evidence["preset_id"] == "quick_standard"


def test_real_preset_evidence_tests_do_not_orchestrate_with_direct_urllib() -> None:
    for path in [
        Path("tests/test_forge_real_local_quick.py"),
        Path("tests/test_forge_real_webapp_portal.py"),
        Path("tests/test_forge_real_repair.py"),
        Path("tests/test_forge_real_greenfield_replay.py"),
    ]:
        text = path.read_text(encoding="utf-8")
        assert "urllib" not in text
        assert "urlopen" not in text
