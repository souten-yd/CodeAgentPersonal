from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read_candidates() -> str:
    texts: list[str] = []
    for path in [ROOT / "run_server.py", ROOT / "scripts"]:
        if path.is_file():
            texts.append(path.read_text(encoding="utf-8", errors="ignore"))
        elif path.is_dir():
            for file in path.rglob("*.py"):
                texts.append(file.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(texts)


def test_launcher_checks_model_status_auto_load_failed() -> None:
    text = _read_candidates()
    assert "auto_load_failed" in text
    assert "auto_load_failure_reason" in text


def test_launcher_surfaces_model_startup_debug_hint() -> None:
    text = _read_candidates()
    assert "/debug/model-startup" in text
    assert "collect_runtime_snapshot.sh" in text


def test_launcher_distinguishes_fastapi_ready_from_llm_ready() -> None:
    text = _read_candidates()
    assert "FastAPI" in text
    assert "LLM" in text
    assert "ready with warnings" in text or "with warnings" in text
