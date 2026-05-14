from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SEARCH_PATHS = [
    ROOT / "main.py",
    ROOT / "app",
    ROOT / "scripts",
    ROOT / "tests",
    ROOT / "docs",
]
RUNTIME_CODE_PATHS = [ROOT / "main.py", ROOT / "app", ROOT / "scripts"]
ALLOWED_SUFFIXES = {".py", ".md", ".txt", ".json", ".bat", ".ps1", ".sh"}


def _read_from_paths(paths: list[Path]) -> str:
    parts: list[str] = []
    current_test = Path(__file__).resolve()
    for path in paths:
        if path.is_file():
            if path.resolve() == current_test:
                continue
            parts.append(path.read_text(encoding="utf-8", errors="ignore"))
        elif path.is_dir():
            for file in path.rglob("*"):
                if file.resolve() == current_test:
                    continue
                if file.suffix.lower() in ALLOWED_SUFFIXES:
                    parts.append(file.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(parts)


def read_texts() -> str:
    return _read_from_paths(SEARCH_PATHS)


def read_runtime_code_texts() -> str:
    return _read_from_paths(RUNTIME_CODE_PATHS)


def test_sbv2_default_model_is_koharune_ami() -> None:
    text = read_texts()
    assert "koharune-ami" in text


def test_qwen_tts_is_not_reintroduced() -> None:
    text = read_runtime_code_texts().lower()
    forbidden_runtime_tokens = [
        "qwen3_tts",
        "qwen3model",
        "_clearqwen3clonestatustimer",
        "_setqwen3cloneplaytoggle",
    ]
    for token in forbidden_runtime_tokens:
        assert token not in text


def test_runpod_does_not_force_pytorch_jit_zero() -> None:
    lines = read_runtime_code_texts().splitlines()
    for line in lines:
        lowered = line.lower()
        if "runpod" in lowered and "pytorch_jit" in lowered and "0" in lowered:
            raise AssertionError(f"Runpod-specific PYTORCH_JIT=0 forcing detected: {line}")


def test_runpod_does_not_auto_prefer_onnx() -> None:
    text = read_runtime_code_texts().lower()
    risky = [
        "prefer_onnx_on_runpod",
        "runpod_prefer_onnx",
        "auto_prefer_onnx",
    ]
    for token in risky:
        assert token not in text


def test_no_import_time_sbv2_warmup_or_model_load_contract() -> None:
    text = read_runtime_code_texts().lower()
    forbidden = [
        "warmup_at_import",
        "load_sbv2_at_import",
        "download_model_at_import",
    ]
    for token in forbidden:
        assert token not in text


def test_sbv2_runtime_defaults_doc_exists() -> None:
    doc = ROOT / "docs" / "sbv2_runtime_defaults.md"
    assert doc.exists()
    text = doc.read_text(encoding="utf-8")
    for token in ["koharune-ami", "PYTORCH_JIT", "ONNX", "safetensors", "warm-up"]:
        assert token in text
