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
    assert hasattr(module, "UsageCollectorPorts")

    assert callable(module.SettingsPort.get_setting)
    assert callable(module.SettingsPort.set_setting)
    assert callable(module.UsageDiagnosticsPort.set_last_usage_diag)
    assert callable(module.UsageDiagnosticsPort.get_last_usage_diag)


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
