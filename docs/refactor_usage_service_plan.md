# Usage service/provider refactor plan

This plan records the service/provider boundary used to move `GET /system/usage`
and `GET /system/usage/debug` out of `main.py` and into `app/api/system.py`.
Conservative default payload helpers and app-state provider lookup helpers live
in `app/api/system.py`, and `main.app` wires compatibility providers into
`app.state`. The usage/debug endpoint migration is complete, and
`collect_system_usage_info()` now lives in `app/services/system_usage.py` behind
`UsageCollectorPorts`. `main.py` keeps `get_system_usage_info()` only as a
compatibility wrapper for existing providers. The `create_app()` signature,
middleware, lifespan, and UI assets stay unchanged.

## Current collector dependencies

`collect_system_usage_info(ports: UsageCollectorPorts, debug_mode: bool = False)`
now combines collection, auto-detection, settings persistence, and diagnostics
update work in the service module. `main.get_system_usage_info()` delegates to
that function using `app.state.system_usage_ports`, preserving the provider
contract while making the dependency boundary explicit.

Runtime and standard-library dependencies:

- `os.name`, `os.cpu_count()`, and `os.getloadavg()` for platform-specific CPU
  and memory fallbacks.
- `/proc/meminfo` through `_read_meminfo_kb()` on Linux-like systems.
- `subprocess.run()` for PowerShell, `nvidia-smi`, `rocm-smi`, and other backend
  probes.
- `json`, `re`, `datetime.now()`, and `time.time()` for parsing,
  timestamps, and cache expiry.
- Windows-only imports and APIs such as `winreg`, PowerShell counters, CIM/WMI,
  PNP device queries, `wmic`, and `dxdiag`.
- Optional `psutil`, imported inside the function, for the preferred CPU/RAM
  usage path.

Internal helper/global dependencies:

- `_read_meminfo_kb()` for Linux RAM fallback data.
- `_select_working_gpu_backend()` for backend auto-selection.
- `_probe_gpu_static()` for fallback static GPU inventory.
- `_windows_dxdiag_cache` guarded by `_usage_diag_lock` for Windows DXDiag VRAM
  cache state.
- `ports.diagnostics.set_last_usage_diag()` to publish the latest parse/selection diagnostics.

## Settings dependencies: `settings_get` / `settings_set`

Usage collection depends on settings in two separate ways:

1. It reads `ports.settings.get_setting("gpu_usage_backend")` to honor an
   explicit runtime GPU usage backend selection.
2. If the selected backend is empty, `auto`, or `none`, it calls
   `_select_working_gpu_backend(ports, "gpu_usage_backend", candidates)`. That
   helper reads the same setting, probes candidate backends, and writes the
   detected backend with `ports.settings.set_setting("gpu_usage_backend", backend)`
   or writes `"none"` when no backend works.

This means a read-only HTTP usage request can persist settings as a side effect.
The service boundary therefore does not hide settings access in a router. It
injects a small settings port:

- `get_setting(key: str) -> str | None`
- `set_setting(key: str, value: str) -> None`

`MainSettingsPort` wraps the existing `settings_get` and `settings_set` helpers
without changing their behavior, while the service module does not import those
helpers directly.

## Diagnostics dependencies: `_last_usage_diag` helpers

The runtime diagnostics global is currently:

- `_last_usage_diag: dict`
- `_usage_diag_lock`
- `_set_last_usage_diag(diag: dict)`
- `_get_last_usage_diag() -> dict`

`collect_system_usage_info()` writes diagnostics on every usage collection via
`ports.diagnostics.set_last_usage_diag()`. The `GET /system/usage/debug`
provider first calls `get_system_usage_info()` and then reads
`app.state.system_usage_diagnostics.get_last_usage_diag()` to return parse
details plus a compact `final_usage` view.

The service injects a diagnostics port rather than reaching into module globals
from the router:

- `set_last_usage_diag(diag: dict[str, Any]) -> None`
- `get_last_usage_diag() -> dict[str, Any]`

`MainUsageDiagnosticsAdapter` delegates directly to the existing helpers so the
lock and copy semantics remain unchanged, while the service module does not
import `_get_last_usage_diag()` or `_set_last_usage_diag()` directly.

## GPU backend auto-detection side effects

Backend selection is not a pure probe. Current candidate order is
platform-dependent:

- Non-Windows: `nvidia-smi`, `rocm-smi`, `nvidia-proc`, `lspci`.
- Windows: `windows-counter`, `nvidia-smi`.

When `gpu_usage_backend` is `auto`, empty, or `none`, usage collection probes
those candidates and persists the first working backend. If no backend works, it
persists `none`. The probes can also spawn external commands and use slow or
cached Windows DXDiag paths. These subprocess, GPU backend auto-detection, Windows DXDiag/WMI/PowerShell,
and platform probe side effects now live in `app/services/system_usage.py` and
can still occur through HTTP requests to `/system/usage` or
`/system/usage/debug`, matching the previous behavior.

## `create_app()` default provider handling

`create_app()` must keep its current signature. The router uses
optional app-state hooks, matching the existing readiness pattern. Earlier PRs
added provider type aliases, conservative unavailable payload helpers, provider
lookup helpers, and the usage/debug routes in `app/api/system.py`.

Current behavior and next-step notes:

- `create_app()` should not receive new arguments.
- The system router now has conservative default usage/debug payload helpers for
  future factory-app use.
- Those defaults avoid settings writes and expensive GPU auto-detection unless
  the desired factory-app contract explicitly opts into those side effects.
- `/system/usage` now lives in `app/api/system.py`; bare `create_app()` returns
  the conservative unavailable payload, while `main.app` serves live data via
  `app.state.system_usage_provider`.
- `/system/usage/debug` now lives in `app/api/system.py`; bare `create_app()`
  returns `default_system_usage_debug_unavailable_payload()`, while `main.app`
  serves the existing debug payload via `app.state.system_usage_debug_provider`.
- `app/services/system_usage.py` now owns `collect_system_usage_info()` and the
  collector helpers while retaining the import side-effect contract. It
  intentionally does not import `main.py`, `settings_get`, `settings_set`,
  `_get_last_usage_diag()`, or `_set_last_usage_diag()`; subprocess/GPU probes
  and settings writes happen only when the collector is called.
- `app/services/system_usage.py` now also includes `InMemoryUsageDiagnostics`, a
  side-effect-free adapter skeleton that satisfies the diagnostics port without
  referencing `main.py` globals.
- PR4.16 follow-up repair is complete: the Windows PDH helper now uses the
  service module's `time` import directly, and the service contract tests guard
  against stale `_mm_time` references that Linux CI would not execute.
- `main.py` now provides `MainSettingsPort` and `MainUsageDiagnosticsAdapter`
  as the live adapters for the service ports. The settings adapter delegates to
  the existing `settings_get()` / `settings_set()` helpers, and the diagnostics
  adapter delegates to the existing `_set_last_usage_diag()` /
  `_get_last_usage_diag()` helpers.
- `main.app.state.system_usage_ports` is now registered with the live settings
  and diagnostics adapters so the next extraction step can receive one explicit
  dependency container.
- `get_system_usage_info()` remains in `main.py` as a compatibility wrapper
  around `collect_system_usage_info(ports=app.state.system_usage_ports, ...)`.
  Settings persistence and diagnostics updates now flow through
  `UsageCollectorPorts`.

## Richer provider injection from `main.app`

`main.app` now provides the compatibility implementation through app state:

- `app.state.system_usage_settings = MainSettingsPort()`
- `app.state.system_usage_diagnostics = MainUsageDiagnosticsAdapter()`
- `app.state.system_usage_ports = UsageCollectorPorts(settings=..., diagnostics=...)`
- `app.state.system_usage_provider = get_system_usage_info`
- `app.state.system_usage_debug_provider = <wrapper that preserves the current
  debug handler shape>`

The debug provider wrapper calls `get_system_usage_info()` before reading
diagnostics through `app.state.system_usage_diagnostics.get_last_usage_diag()`,
because that is the existing `/system/usage/debug` contract. It does not alter
the `final_usage` shape or the fallback values.

## Move `/system/usage` and `/system/usage/debug` together or separately?

Move them in two staged implementation PRs, but design their service dependency
ports together.

1. Done: add the service/provider skeleton and `main.app` app-state wiring while
   the inline endpoints still serve traffic. Keep endpoint behavior unchanged
   and verify the inventory contract.
2. Done: move `/system/usage` to `app/api/system.py` using the provider hook.
   Provider-less factory apps return `default_system_usage_unavailable_payload()`,
   while `main.app` preserves existing behavior through
   `app.state.system_usage_provider = get_system_usage_info`.
3. Done: move `/system/usage/debug` to `app/api/system.py` using the debug
   provider hook. The provider preserves the exact current sequence: collect
   fresh usage, read last diagnostics, then format the debug payload.

The reason not to move debug before the provider contract was that it depends
on the side effects of the usage collector. With the router/provider boundary and service collector in place, the
usage/debug endpoint migration and collector extraction are complete. Future work
should continue treating settings persistence, GPU backend auto-detection,
subprocess probes, OS probes, Windows DXDiag/WMI/PowerShell probes, and other
platform side effects deliberately so endpoint contracts stay unchanged. The
next candidates remain `/system/summary` providerization or settings router
inventory.
