import importlib
import inspect
import sys
from typing import Any, get_type_hints


def test_system_usage_service_module_imports_without_main_side_effects():
    sys.modules.pop("app.services.system_usage", None)
    sys.modules.pop("app.services", None)
    sys.modules.pop("main", None)

    module = importlib.import_module("app.services.system_usage")

    assert module.__name__ == "app.services.system_usage"
    assert "main" not in sys.modules


def test_system_usage_service_ports_exist_with_expected_methods():
    module = importlib.import_module("app.services.system_usage")

    assert hasattr(module, "SettingsPort")
    assert hasattr(module, "UsageDiagnosticsPort")
    assert hasattr(module, "InMemoryUsageDiagnostics")
    assert hasattr(module, "UsageCollectorPorts")

    assert callable(module.SettingsPort.get_setting)
    assert callable(module.SettingsPort.set_setting)
    assert callable(module.UsageDiagnosticsPort.set_last_usage_diag)
    assert callable(module.UsageDiagnosticsPort.get_last_usage_diag)
    assert callable(module.InMemoryUsageDiagnostics.set_last_usage_diag)
    assert callable(module.InMemoryUsageDiagnostics.get_last_usage_diag)


def test_system_usage_service_port_type_contracts():
    module = importlib.import_module("app.services.system_usage")

    settings_get_hints = get_type_hints(module.SettingsPort.get_setting)
    settings_set_hints = get_type_hints(module.SettingsPort.set_setting)
    diag_set_hints = get_type_hints(module.UsageDiagnosticsPort.set_last_usage_diag)
    diag_get_hints = get_type_hints(module.UsageDiagnosticsPort.get_last_usage_diag)
    collector_hints = get_type_hints(module.UsageCollectorPorts)

    assert settings_get_hints == {"key": str, "return": str | None}
    assert settings_set_hints == {"key": str, "value": str, "return": type(None)}
    assert diag_set_hints == {"diag": dict[str, Any], "return": type(None)}
    assert diag_get_hints == {"return": dict[str, Any]}
    assert collector_hints == {
        "settings": module.SettingsPort,
        "diagnostics": module.UsageDiagnosticsPort,
    }


def test_in_memory_usage_diagnostics_satisfies_port_and_preserves_values():
    module = importlib.import_module("app.services.system_usage")

    diagnostics = module.InMemoryUsageDiagnostics()

    assert isinstance(diagnostics, module.UsageDiagnosticsPort)

    diagnostics.set_last_usage_diag({"backend": "nvidia-smi", "ok": True})

    assert diagnostics.get_last_usage_diag() == {"backend": "nvidia-smi", "ok": True}


def test_in_memory_usage_diagnostics_get_returns_copy():
    module = importlib.import_module("app.services.system_usage")
    diagnostics = module.InMemoryUsageDiagnostics()

    diagnostics.set_last_usage_diag({"backend": "nvidia-smi", "ok": True})
    snapshot = diagnostics.get_last_usage_diag()
    snapshot["backend"] = "mutated"
    snapshot["new"] = "external"

    assert diagnostics.get_last_usage_diag() == {"backend": "nvidia-smi", "ok": True}


def test_in_memory_usage_diagnostics_set_copies_input():
    module = importlib.import_module("app.services.system_usage")
    diagnostics = module.InMemoryUsageDiagnostics()
    source = {"backend": "nvidia-smi", "ok": True}

    diagnostics.set_last_usage_diag(source)
    source["backend"] = "mutated"

    assert diagnostics.get_last_usage_diag() == {"backend": "nvidia-smi", "ok": True}


def test_system_usage_numeric_helpers_keep_existing_shapes():
    module = importlib.import_module("app.services.system_usage")

    assert module._parse_int_maybe("12,345") == 12345
    assert module._parse_int_maybe(" 007 ") == 7
    assert module._parse_int_maybe("12.3") == -1
    assert module._parse_int_maybe("-5") == -1
    assert module._parse_int_maybe(None) == -1

    assert module._bytes_to_mb(2 * 1024 * 1024) == 2
    assert module._bytes_to_mb(1536 * 1024) == 1
    assert module._bytes_to_mb("1048576") == -1

    assert module._kb_to_mb(2048) == 2
    assert module._kb_to_mb(1536) == 1
    assert module._kb_to_mb(None) == -1


def test_system_usage_percent_and_timestamp_helpers_handle_edge_cases():
    module = importlib.import_module("app.services.system_usage")

    assert module._calculate_percent(25, 100) == 25.0
    assert module._calculate_percent(1, 4) == 25.0
    assert module._calculate_percent(-1, 100) == -1.0
    assert module._calculate_percent(1, 0) == -1.0

    timestamp = module._usage_updated_at()
    assert isinstance(timestamp, str)
    assert timestamp


def test_system_usage_static_gpu_normalizer_keeps_response_keys():
    module = importlib.import_module("app.services.system_usage")

    assert module._normalize_static_gpu_usage({"name": "GPU 0", "memory_total_mb": 8192}) == {
        "name": "GPU 0",
        "util_percent": -1,
        "vram_used_mb": -1,
        "vram_total_mb": 8192,
        "vram_percent": -1,
    }
    assert module._normalize_static_gpu_usage({}) == {
        "name": "GPU",
        "util_percent": -1,
        "vram_used_mb": -1,
        "vram_total_mb": -1,
        "vram_percent": -1,
    }

class _FakeSettings:
    def __init__(self):
        self.values = {"gpu_usage_backend": "auto"}
        self.calls = []

    def get_setting(self, key: str) -> str | None:
        self.calls.append(("get", key))
        return self.values.get(key)

    def set_setting(self, key: str, value: str) -> None:
        self.calls.append(("set", key, value))
        self.values[key] = value


def test_collect_system_usage_info_exists_and_uses_ports_without_external_gpu_commands(monkeypatch):
    module = importlib.import_module("app.services.system_usage")

    assert callable(module.collect_system_usage_info)

    settings = _FakeSettings()
    diagnostics = module.InMemoryUsageDiagnostics()
    ports = module.UsageCollectorPorts(settings=settings, diagnostics=diagnostics)

    def fake_probe(backend: str) -> list[dict[str, Any]]:
        assert backend == "nvidia-smi"
        return [{"name": "Static GPU", "memory_total_mb": 8192, "memory_free_mb": 4096}]

    class FakeCompleted:
        returncode = 0
        stdout = "Test GPU, 42, 2048, 8192\n"
        stderr = ""

    def fake_run(cmd, *args, **kwargs):
        assert cmd[0] == "nvidia-smi"
        return FakeCompleted()

    monkeypatch.setattr(module, "_probe_gpu_static", fake_probe)
    monkeypatch.setattr(module.subprocess, "run", fake_run)

    payload = module.collect_system_usage_info(ports=ports, debug_mode=True)
    diag = diagnostics.get_last_usage_diag()

    assert payload["gpu_backend_selected"] == "nvidia-smi"
    assert payload["gpu_backend"] == "nvidia-smi"
    assert payload["vram_source_backend"] == "nvidia-smi"
    assert payload["vram_confidence"] == "direct"
    assert payload["gpus"] == [
        {
            "name": "Test GPU",
            "util_percent": 42.0,
            "vram_used_mb": 2048,
            "vram_total_mb": 8192,
            "vram_percent": 25.0,
        }
    ]
    assert isinstance(payload["updated_at"], str)
    assert ("get", "gpu_usage_backend") in settings.calls
    assert ("set", "gpu_usage_backend", "nvidia-smi") in settings.calls
    assert diag["gpu_backend_selected"] == "nvidia-smi"
    assert diag["gpu_backend"] == "nvidia-smi"
    assert diag["parse_source"] == "direct"
    assert diag["adopted_values"]["gpu_count"] == 1


def test_system_usage_service_source_has_no_stale_mm_time_reference():
    module = importlib.import_module("app.services.system_usage")

    assert "_mm_time" not in inspect.getsource(module)


def test_windows_counter_collection_falls_back_without_pdh_side_effects(monkeypatch):
    module = importlib.import_module("app.services.system_usage")

    settings = _FakeSettings()
    settings.values["gpu_usage_backend"] = "windows-counter"
    diagnostics = module.InMemoryUsageDiagnostics()
    ports = module.UsageCollectorPorts(settings=settings, diagnostics=diagnostics)

    class FakeVirtualMemory:
        total = 8 * 1024 * 1024
        available = 4 * 1024 * 1024
        percent = 50.0

    class FakePsutil:
        @staticmethod
        def cpu_percent(interval=0.15):
            return 12.5

        @staticmethod
        def virtual_memory():
            return FakeVirtualMemory()

    def fake_run(*args, **kwargs):
        raise FileNotFoundError("Windows probes are unavailable in this test")

    monkeypatch.setattr(module.os, "name", "nt")
    monkeypatch.setitem(sys.modules, "psutil", FakePsutil)
    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setattr(module, "_probe_gpu_static", lambda backend: [])

    payload = module.collect_system_usage_info(ports=ports, debug_mode=False)
    diag = diagnostics.get_last_usage_diag()

    assert payload["gpu_backend_selected"] == "windows-counter"
    assert payload["gpu_backend"] == "windows-counter"
    assert payload["gpus"] == []
    assert payload["cpu_percent"] == 12.5
    assert payload["ram_total_mb"] == 8
    assert payload["ram_used_mb"] == 4
    assert diag["gpu_backend_selected"] == "windows-counter"
    assert diag["parse_source"] == "unknown"

def test_system_usage_service_import_does_not_probe_or_persist(monkeypatch):
    sys.modules.pop("app.services.system_usage", None)
    sys.modules.pop("main", None)

    import subprocess

    def fail_run(*args, **kwargs):
        raise AssertionError("subprocess probe must not run during import")

    monkeypatch.setattr(subprocess, "run", fail_run)

    module = importlib.import_module("app.services.system_usage")

    assert callable(module.collect_system_usage_info)
    assert "main" not in sys.modules
