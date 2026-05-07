# Usage service/provider refactor plan

This plan records the service/provider boundary used to move `GET /system/usage`
out of `main.py` and into `app/api/system.py`. Conservative default payload
helpers and app-state provider lookup helpers live in `app/api/system.py`, and
`main.app` wires compatibility providers into `app.state`.
`GET /system/usage/debug`, `get_system_usage_info()`, settings behavior,
diagnostics globals, the `create_app()` signature, middleware, lifespan, and UI
assets stay unchanged in this PR. Debug endpoint migration is explicitly left
for the next PR.

## Current `get_system_usage_info()` dependencies

`get_system_usage_info(debug_mode: bool = False)` currently combines collection,
auto-detection, settings persistence, and diagnostics update work in one
function. The endpoint should not be routerized until these dependencies are
made explicit.

Runtime and standard-library dependencies:

- `os.name`, `os.cpu_count()`, and `os.getloadavg()` for platform-specific CPU
  and memory fallbacks.
- `/proc/meminfo` through `_read_meminfo_kb()` on Linux-like systems.
- `subprocess.run()` for PowerShell, `nvidia-smi`, `rocm-smi`, and other backend
  probes.
- `json`, `re`, `datetime.now()`, and `_mm_time.time()` for parsing,
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
- `_set_last_usage_diag()` to publish the latest parse/selection diagnostics.

## Settings dependencies: `settings_get` / `settings_set`

Usage collection depends on settings in two separate ways:

1. It reads `settings_get("gpu_usage_backend")` to honor an explicit runtime GPU
   usage backend selection.
2. If the selected backend is empty, `auto`, or `none`, it calls
   `_select_working_gpu_backend("gpu_usage_backend", candidates)`. That helper
   reads the same setting, probes candidate backends, and writes the detected
   backend with `settings_set("gpu_usage_backend", backend)` or writes
   `"none"` when no backend works.

This means a read-only HTTP usage request can persist settings as a side effect.
The future service boundary should therefore not hide settings access in a
router. It should inject a small settings port, for example:

- `get_setting(key: str) -> str | None`
- `set_setting(key: str, value: str) -> None`

The first provider skeleton can wrap existing `settings_get` and `settings_set`
without changing their behavior.

## Diagnostics dependencies: `_last_usage_diag` helpers

The runtime diagnostics global is currently:

- `_last_usage_diag: dict`
- `_usage_diag_lock`
- `_set_last_usage_diag(diag: dict)`
- `_get_last_usage_diag() -> dict`

`get_system_usage_info()` writes diagnostics on every usage collection. The
`GET /system/usage/debug` handler first calls `get_system_usage_info()` and then
reads `_get_last_usage_diag()` to return parse details plus a compact
`final_usage` view.

A future service should inject a diagnostics port rather than reaching into
module globals from the router:

- `set_last_usage_diag(diag: dict[str, Any]) -> None`
- `get_last_usage_diag() -> dict[str, Any]`

The initial richer provider in `main.app` can delegate directly to the existing
helpers so the lock and copy semantics remain unchanged.

## GPU backend auto-detection side effects

Backend selection is not a pure probe. Current candidate order is
platform-dependent:

- Non-Windows: `nvidia-smi`, `rocm-smi`, `nvidia-proc`, `lspci`.
- Windows: `windows-counter`, `nvidia-smi`.

When `gpu_usage_backend` is `auto`, empty, or `none`, usage collection probes
those candidates and persists the first working backend. If no backend works, it
persists `none`. The probes can also spawn external commands and use slow or
cached Windows DXDiag paths. The service boundary should make this explicit in
naming and docs, for example `collect_usage_with_backend_autodetect()`, rather
than presenting it as a pure payload formatter.

## `create_app()` default provider handling

`create_app()` must keep its current signature. The router can eventually look
for optional app-state hooks, matching the existing readiness pattern. This PR
adds provider type aliases, conservative unavailable payload helpers, and
provider lookup helpers in `app/api/system.py`, but it does not add the usage or
debug usage routes to that router.

Recommended next-step behavior:

- `create_app()` should not receive new arguments.
- The system router now has conservative default usage/debug payload helpers for
  future factory-app use.
- Those defaults avoid settings writes and expensive GPU auto-detection unless
  the desired factory-app contract explicitly opts into those side effects.
- `/system/usage` now lives in `app/api/system.py`; bare `create_app()` returns
  the conservative unavailable payload, while `main.app` serves live data via
  `app.state.system_usage_provider`.

## Richer provider injection from `main.app`

`main.app` now provides the compatibility implementation through app state:

- `app.state.system_usage_provider = get_system_usage_info`
- `app.state.system_usage_debug_provider = <wrapper that preserves the current
  debug handler shape>`

The debug provider wrapper calls `get_system_usage_info()` before reading
`_get_last_usage_diag()`, because that is the existing `/system/usage/debug`
contract. It does not alter the `final_usage` shape or the fallback values.

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
3. Next PR: move `/system/usage/debug` after the debug provider contract proves
   the exact current sequence: collect fresh usage, read last diagnostics, then
   format the debug payload. `/system/usage/debug` remains in `main.py` for now.

The reason not to move debug first is that it depends on the side effects of the
usage collector. The reason not to move both before extracting the provider
boundary is that both endpoints would otherwise import settings and diagnostics
globals directly into the router.
