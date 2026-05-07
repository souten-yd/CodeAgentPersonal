import importlib
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
