from pathlib import Path

from fastapi.testclient import TestClient

from app.api.runtime_controls import (
    CUDA_REGRESSION_BASELINE_REF,
    CUDA_REGRESSION_SUSPECTED_FILES,
    default_runtime_cuda_debug_payload,
)
from app.server import create_app


DOC_PATH = Path("docs/cuda_regression_v2_7_diff.md")
SERVER_PATH = Path("app/server.py")
MAIN_PATH = Path("main.py")


def test_v2_7_cuda_regression_diff_doc_records_required_inventory():
    text = DOC_PATH.read_text(encoding="utf-8")

    assert "KasaneCore_v2.7" in text
    assert "26 commits ahead" in text
    for path in [
        "app/server.py",
        "main.py",
        "app/api/runtime_controls.py",
        "app/api/echo.py",
        "app/api/jobs.py",
        "app/api/nexus.py",
        "app/services/jobs.py",
        "app/audio/runtime_config.py",
        "app/asr/service.py",
        "app/tts/style_bert_vits2_runtime.py",
    ]:
        assert path in text


def test_v2_7_diff_doc_states_docker_launcher_scope():
    text = DOC_PATH.read_text(encoding="utf-8")

    for path in [
        "Dockerfile",
        "docker/start-services.sh",
        "setup_whisper_cpp_vulkan_windows.bat",
        "setup_style_bert_vits2_windows.bat",
        "DLllama.bat",
    ]:
        assert path in text
    assert "no diff" in text.lower()
    assert "not Docker image construction" in text


def test_runtime_cuda_debug_fallback_contains_v2_7_baseline_fields():
    payload = default_runtime_cuda_debug_payload()

    assert payload["baseline_ref"] == CUDA_REGRESSION_BASELINE_REF == "KasaneCore_v2.7"
    assert payload["changed_since_baseline"] is True
    assert payload["import_time_probe_detected"] is False
    assert set(CUDA_REGRESSION_SUSPECTED_FILES).issubset(payload["suspected_changed_files"])
    for key in [
        "torch_cuda_available",
        "torch_cuda_error",
        "ctranslate2_cuda_available",
        "ctranslate2_cuda_error",
        "llama_cuda_validation_reason",
    ]:
        assert key in payload


def test_create_app_runtime_cuda_debug_exposes_v2_7_baseline_without_provider():
    app = create_app()
    client = TestClient(app)

    response = client.get("/runtime/cuda-debug")

    assert response.status_code == 200
    payload = response.json()
    assert payload["baseline_ref"] == "KasaneCore_v2.7"
    assert payload["changed_since_baseline"] is True
    assert payload["import_time_probe_detected"] is False
    assert set(CUDA_REGRESSION_SUSPECTED_FILES).issubset(payload["suspected_changed_files"])


def test_main_no_longer_runs_detect_audio_runtime_for_asr_globals_at_import_time():
    source = MAIN_PATH.read_text(encoding="utf-8")
    asr_section = source.split("# 音声入力（Whisper / CPUオンデマンド）", maxsplit=1)[1].split("_VOICE_MODEL_CANDIDATES", maxsplit=1)[0]

    assert "_audio_runtime_initial = detect_audio_runtime()" not in asr_section
    assert '_voice_device = ""' in asr_section
    assert '_voice_compute_type = ""' in asr_section
    assert "def _voice_runtime_device_for_status" in asr_section


def test_app_server_lazy_router_import_contract_is_documented_in_source():
    source = SERVER_PATH.read_text(encoding="utf-8")
    include_body = source.split("def include_routers", maxsplit=1)[1]

    assert "Router modules are imported lazily" in include_body
    assert "from app.api.runtime_controls import router as runtime_controls_router" in include_body
