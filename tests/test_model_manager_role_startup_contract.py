import main


def test_role_override_resolves_slugged_model_name(monkeypatch):
    catalog = {
        "qwen3_6_27b_iq4_xs": {
            "model_key": "qwen3_6_27b_iq4_xs",
            "name": "Qwen3.6-27B-IQ4_XS",
            "path": "E:/LLMs/Qwen3.6-27B-IQ4_XS.gguf",
            "auto_roles": [],
        },
        "gemma_4_e4b_it_q4_k_m": {
            "model_key": "gemma_4_e4b_it_q4_k_m",
            "name": "Gemma",
            "path": "/models/gemma-4-E4B-it-Q4_K_M.gguf",
            "auto_roles": ["chat"],
        },
    }
    monkeypatch.setattr(main, "MODEL_ROLE_OPTIONS", ("plan", "chat"))
    monkeypatch.setattr(
        main,
        "settings_get",
        lambda key: "Qwen3.6-27B-IQ4_XS" if key == "role_model_plan" else "",
    )

    task_map = main.get_runtime_task_model_map(catalog, include_disabled=True)

    assert task_map["plan"] == "qwen3_6_27b_iq4_xs"
    assert task_map["chat"] == "gemma_4_e4b_it_q4_k_m"


def test_startup_model_prefers_resolved_plan_override_and_skips_local_bundled_gemma(monkeypatch, tmp_path):
    qwen = tmp_path / "Qwen3.6-27B-IQ4_XS.gguf"
    qwen.write_text("fake", encoding="utf-8")
    catalog = {
        "gemma_4_e4b_it_q4_k_m": {
            "model_key": "gemma_4_e4b_it_q4_k_m",
            "name": "Gemma 4 E4B IT Q4_K_M",
            "path": "/models/gemma-4-E4B-it-Q4_K_M.gguf",
            "auto_roles": ["chat"],
        },
        "qwen3_6_27b_iq4_xs": {
            "model_key": "qwen3_6_27b_iq4_xs",
            "name": "Qwen3.6-27B-IQ4_XS",
            "path": str(qwen),
            "auto_roles": [],
        },
    }
    rows = [
        {
            "model_key": "gemma_4_e4b_it_q4_k_m",
            "name": "Gemma 4 E4B IT Q4_K_M",
            "path": "/models/gemma-4-E4B-it-Q4_K_M.gguf",
            "enabled": 1,
            "notes": "filename=gemma-4-E4B-it-Q4_K_M.gguf",
        },
        {
            "model_key": "qwen3_6_27b_iq4_xs",
            "name": "Qwen3.6-27B-IQ4_XS",
            "path": str(qwen),
            "enabled": 1,
        },
    ]
    monkeypatch.setattr(main, "IS_RUNPOD_RUNTIME", False)
    monkeypatch.setattr(main, "MODEL_ROLE_OPTIONS", ("plan", "chat", "code"))
    monkeypatch.setattr(main, "get_runtime_model_catalog", lambda include_disabled=False: catalog)
    monkeypatch.setattr(main, "model_db_list", lambda: rows)
    monkeypatch.setattr(
        main,
        "settings_get",
        lambda key: str(qwen) if key == "role_model_plan" else "",
    )

    assert main._choose_default_startup_model() == "qwen3_6_27b_iq4_xs"


def test_ensure_model_logs_missing_path_substitution(monkeypatch):
    manager = main.ModelManager.__new__(main.ModelManager)
    manager._last_startup_hints = []
    manager.current_key = ""
    manager._status = "idle"
    manager._catalog = lambda: {
        "gemma_4_e4b_it_q4_k_m": {"name": "Gemma", "path": ""},
        "qwen3_6_27b_iq4_xs": {"name": "Qwen", "path": "E:/LLMs/qwen.gguf", "llm_url": ""},
    }
    manager._task_model_map = lambda: {"chat": "qwen3_6_27b_iq4_xs"}
    switched = {}
    manager._switch = lambda key, on_event=None: switched.setdefault("key", key) == key

    assert manager.ensure_model("gemma_4_e4b_it_q4_k_m") is True

    assert switched["key"] == "qwen3_6_27b_iq4_xs"
    assert any("substituted 'qwen3_6_27b_iq4_xs'" in hint for hint in manager._last_startup_hints)


def test_llama_startup_failure_classification_patterns():
    assert main._classify_llama_startup_failure_text("ggml_backend_alloc: failed to allocate buffer") == "oom"
    assert main._classify_llama_startup_failure_text("HIP error: hipErrorNoBinaryForGpu unsupported gfx1201") == "gpu_unsupported"
    assert main._classify_llama_startup_failure_text("error loading model architecture") == "model_load_error"


def test_windows_amd_retries_oom_with_lower_ngl(monkeypatch):
    manager = main.ModelManager.__new__(main.ModelManager)
    manager._last_startup_failure_reason = "unknown"
    attempts = []
    saved = {}

    def fake_try(spec, gpu_layers, eff_ck, eff_cv, gpu_vendor, emit):
        attempts.append(gpu_layers)
        if gpu_layers is None:
            manager._last_startup_failure_reason = "oom"
            return "oom"
        return "ok"

    manager._try_start_once = fake_try
    manager._parse_ngl_from_log = lambda: None
    manager._save_proven_ngl = lambda spec, ngl: saved.setdefault("ngl", ngl)
    manager._kill_process = lambda: None
    spec = {"name": "Qwen", "gpu_layers": 80}

    ok = manager._start_windows(
        spec,
        eff_ck="q8_0",
        eff_cv="q8_0",
        gpu_vendor="amd",
        emit=lambda *args: None,
        calc_gpu_layers=80,
        proven_ngl=-1,
    )

    assert ok is True
    assert attempts == [None, 40]
    assert saved["ngl"] == 40
