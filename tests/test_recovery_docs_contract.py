from pathlib import Path


REQUIRED_PATHS = [
    Path("docs/runbooks/runpod_cuda_recovery.md"),
    Path("docs/runbooks/known_good_runtime_baseline.md"),
    Path("docs/feature_inventory.md"),
    Path("docs/api_route_ownership_inventory.md"),
    Path("docs/refactor_recovery_map.md"),
    Path("scripts/collect_runtime_snapshot.sh"),
    Path("scripts/export_route_inventory.py"),
    Path("scripts/check_runtime_baseline.py"),
]


def test_recovery_docs_and_tools_exist():
    for path in REQUIRED_PATHS:
        assert path.exists(), f"missing recovery artifact: {path}"
        assert path.read_text(encoding="utf-8").strip(), f"empty recovery artifact: {path}"


def test_runbook_records_known_good_recovery_points_and_invariants():
    runbook_text = Path("docs/runbooks/runpod_cuda_recovery.md").read_text(encoding="utf-8")
    baseline_text = Path("docs/runbooks/known_good_runtime_baseline.md").read_text(encoding="utf-8")
    combined = runbook_text + "\n" + baseline_text

    assert "KasaneCore_v2.7" in combined
    assert "PR4.50.1 / #963" in combined
    assert "detect_audio_runtime()" in combined
    assert "import 時" in combined or "import-time" in combined
    assert "app.server" in combined
    assert "lazy import" in combined


def test_runtime_snapshot_script_collects_required_diagnostics():
    script = Path("scripts/collect_runtime_snapshot.sh").read_text(encoding="utf-8")

    for endpoint_name in [
        "health",
        "system_summary",
        "cuda_debug",
        "audio_runtime_debug",
        "voice_status",
        "models_db_status",
        "llm_ctx",
        "llm_props",
        "nexus_web_status",
        "echo_save_status",
    ]:
        assert endpoint_name in script

    for required_text in [
        "nvidia-smi",
        "CUDA_VISIBLE_DEVICES",
        "NVIDIA_VISIBLE_DEVICES",
        "/dev/nvidia*",
        "torch.cuda.is_available",
        "ctranslate2.get_cuda_device_count",
        "llama-server",
        "ldd",
        "container_log_tail.txt",
        "/workspace/ca_data/debug_runtime_snapshots",
    ]:
        assert required_text in script


def test_route_inventory_and_baseline_scripts_are_safe_to_import():
    route_script = Path("scripts/export_route_inventory.py").read_text(encoding="utf-8")
    baseline_script = Path("scripts/check_runtime_baseline.py").read_text(encoding="utf-8")

    assert "app.server:create_app()" in route_script
    assert "--app main:app" in route_script
    assert "urlopen" in baseline_script
    assert "does not force LLM generation" in baseline_script
    assert "ASR transcription" in baseline_script
    assert "TTS synthesis" in baseline_script
