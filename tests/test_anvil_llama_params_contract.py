"""Anvil per-model llama-server parameters: Models DB persistence + launch command.

Covers the new first-class columns (n_cpu_moe, flash_attn, no_mmap, jinja, reasoning,
spec_type, spec_draft_*, temp/top_p/top_k/min_p/presence_penalty/repeat_penalty) end to end:
they round-trip through the Models DB, flow into _runtime_spec_from_row, and are emitted as the
matching llama-server flags by _try_start_once. Sentinels (-1/'' ) omit the flag; 0.0 is a real
value (temp/min_p) and must still be emitted.
"""
from pathlib import Path
from unittest import mock

import requests

import main


# ----- Models DB round-trip -----

def test_model_db_roundtrips_new_llama_params(tmp_path):
    db_path = str(tmp_path / "model_db.db")
    with mock.patch.object(main, "MODEL_DB_PATH", db_path):
        mid = main.model_db_add({
            "name": "Qwen3.6", "path": str(tmp_path / "qwen.gguf"), "model_key": "qwen36",
            "ctx_size": 16384, "gpu_layers": 999, "threads": 16, "parallel": 1,
            "batch_size": 2048, "ubatch_size": 256, "cache_type_k": "q8_0", "cache_type_v": "q8_0",
            "n_cpu_moe": 14, "flash_attn": 1, "no_mmap": 1, "jinja": 1, "reasoning": "off",
            "spec_type": "draft-mtp", "spec_draft_n_max": 2, "spec_draft_p_min": 0.75,
            "temp": 0.7, "top_p": 0.8, "top_k": 20, "min_p": 0.0,
            "presence_penalty": 1.5, "repeat_penalty": 1.0,
        })
        rows = main.model_db_list()
        row = next(r for r in rows if r["id"] == mid)
        assert row["n_cpu_moe"] == 14
        assert row["spec_type"] == "draft-mtp"
        assert row["spec_draft_p_min"] == 0.75
        assert row["temp"] == 0.7
        assert row["min_p"] == 0.0
        assert row["flash_attn"] == 1

        # Update a subset and confirm it persists (PUT /models/db path).
        main.model_db_update(mid, {"temp": 0.3, "n_cpu_moe": 24, "spec_type": "draft-model"})
        row2 = next(r for r in main.model_db_list() if r["id"] == mid)
        assert row2["temp"] == 0.3
        assert row2["n_cpu_moe"] == 24
        assert row2["spec_type"] == "draft-model"

        # _runtime_spec_from_row carries the values, preserving 0.0 (not collapsed to the sentinel).
        spec = main._runtime_spec_from_row(row)
        assert spec["n_cpu_moe"] == 14
        assert spec["spec_draft_p_min"] == 0.75
        assert spec["min_p"] == 0.0
        assert spec["temp"] == 0.7


def test_spec_sentinel_helpers_preserve_zero():
    assert main._spec_int_or_unset(None) == -1
    assert main._spec_int_or_unset("") == -1
    assert main._spec_int_or_unset(0) == 0
    assert main._spec_float_or_unset(None) == -1.0
    assert main._spec_float_or_unset(0.0) == 0.0
    assert main._format_llama_float(0.75) == "0.75"
    assert main._format_llama_float(1.0) == "1"
    assert main._format_llama_float(0.0) == "0"


# ----- launch command construction -----

class _FakeResponse:
    status_code = 200


class _FakePopen:
    def __init__(self, cmd, stdout=None, stderr=None, creationflags=0):
        self.cmd = cmd
        self.pid = 12345
        self.returncode = None

    def poll(self):
        return None

    def terminate(self):
        self.returncode = 0

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.returncode = -9


def _manager(tmp_path, monkeypatch):
    llama = tmp_path / "llama-server"
    model = tmp_path / "model.gguf"
    llama.write_text("#!/bin/sh\n", encoding="utf-8")
    model.write_text("fake", encoding="utf-8")

    manager = main.ModelManager.__new__(main.ModelManager)
    manager.llama_path = str(llama)
    manager.llm_port = 18080
    manager._process = None
    manager._status = "ready"
    manager._switch_eta = 9999999999
    manager._last_start_cmd = ""
    manager._last_startup_hints = []
    manager._last_llama_gpu_log = {}
    manager._last_runtime_decision = {}
    manager._last_nvidia_smi_before = []
    manager._last_nvidia_smi_after = []
    manager._last_ngl_search_debug = {}
    manager.last_model_load_status = "idle"
    manager.last_model_load_error = None
    manager.last_gpu_validation_status = "pending"
    manager.last_gpu_validation_reason = None
    manager.last_gpu_validation_path = None
    manager._startup_log_fd = None

    monkeypatch.setattr(manager, "_collect_nvidia_smi_memory", lambda: [])
    monkeypatch.setattr(requests, "get", lambda *a, **k: _FakeResponse())
    monkeypatch.setattr(main, "LLAMA_STARTUP_LOG_PATH", str(tmp_path / "llama_startup.log"))

    spec = {
        "name": "Qwen3.6", "path": str(model), "ctx": 16384, "threads": 16,
        "load_sec": 60, "gpu_layers": 999, "proven_ngl": 999, "extra_args": [],
        "parallel": 1, "batch_size": 2048, "ubatch_size": 256,
        "n_cpu_moe": 14, "flash_attn": 1, "no_mmap": 1, "jinja": 1, "reasoning": "off",
        "spec_type": "draft-mtp", "spec_draft_n_max": 2, "spec_draft_p_min": 0.75,
        "temp": 0.7, "top_p": 0.8, "top_k": 20, "min_p": 0.0,
        "presence_penalty": 1.5, "repeat_penalty": 1.0,
    }
    return manager, spec


def _flag_value(cmd, flag):
    return cmd[cmd.index(flag) + 1]


def test_try_start_emits_full_llama_param_set(tmp_path, monkeypatch):
    captured = {}
    monkeypatch.setattr(main._sp, "Popen",
                        lambda cmd, stdout=None, stderr=None, creationflags=0:
                        captured.setdefault("cmd", cmd) or _FakePopen(cmd))
    manager, spec = _manager(tmp_path, monkeypatch)

    result = manager._try_start_once(spec, gpu_layers=999, eff_ck="q8_0", eff_cv="q8_0",
                                     gpu_vendor="nvidia", emit=lambda *a: None)
    assert result == "ok"
    cmd = captured["cmd"]

    assert _flag_value(cmd, "--n-cpu-moe") == "14"
    assert _flag_value(cmd, "--flash-attn") == "on"
    assert "--no-mmap" in cmd
    assert "--jinja" in cmd
    assert _flag_value(cmd, "--reasoning") == "off"
    assert _flag_value(cmd, "--spec-type") == "draft-mtp"
    assert _flag_value(cmd, "--spec-draft-n-max") == "2"
    assert _flag_value(cmd, "--spec-draft-p-min") == "0.75"
    assert _flag_value(cmd, "--temp") == "0.7"
    assert _flag_value(cmd, "--top-p") == "0.8"
    assert _flag_value(cmd, "--top-k") == "20"
    assert _flag_value(cmd, "--min-p") == "0"          # 0.0 is a real value, still emitted
    assert _flag_value(cmd, "--presence-penalty") == "1.5"
    assert _flag_value(cmd, "--repeat-penalty") == "1"
    assert _flag_value(cmd, "--parallel") == "1"
    assert _flag_value(cmd, "--batch-size") == "2048"
    assert _flag_value(cmd, "--ubatch-size") == "256"


def test_try_start_omits_unset_params_and_respects_flash_no_mmap_off(tmp_path, monkeypatch):
    captured = {}
    monkeypatch.setattr(main._sp, "Popen",
                        lambda cmd, stdout=None, stderr=None, creationflags=0:
                        captured.setdefault("cmd", cmd) or _FakePopen(cmd))
    manager, _ = _manager(tmp_path, monkeypatch)

    # Minimal spec: new params unset (sentinels) -> flags omitted; flash_attn/no_mmap explicit OFF.
    spec = {
        "name": "Bare", "path": str(tmp_path / "model.gguf"), "ctx": 8192, "threads": 8,
        "load_sec": 60, "gpu_layers": 999, "proven_ngl": 999, "extra_args": [],
        "flash_attn": 0, "no_mmap": 0,
    }
    result = manager._try_start_once(spec, gpu_layers=999, eff_ck="q8_0", eff_cv="q8_0",
                                     gpu_vendor="nvidia", emit=lambda *a: None)
    assert result == "ok"
    cmd = captured["cmd"]

    assert "--no-mmap" not in cmd                 # explicit OFF
    assert _flag_value(cmd, "--flash-attn") == "off"  # explicit OFF overrides nvidia default
    for flag in ("--n-cpu-moe", "--jinja", "--reasoning", "--spec-type",
                 "--spec-draft-n-max", "--spec-draft-p-min", "--temp", "--top-p",
                 "--top-k", "--min-p", "--presence-penalty", "--repeat-penalty"):
        assert flag not in cmd
