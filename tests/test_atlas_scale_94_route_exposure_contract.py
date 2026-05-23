from pathlib import Path

SCAN_FILES = [
    "app/api/atlas_pipeline.py",
    "app/server.py",
    "main.py",
    "app/atlas/level1_guarded_execution.py",
    "web/atlas-next/src/api/atlasClient.ts",
]

FORBIDDEN_ROUTE_MARKERS = [
    "/api/atlas/level1/execute",
    "/api/atlas/execute",
    "/safe-apply/execute",
    "/auto-safe-apply",
    "/auto-safe-apply-and-verify",
    "/dry-run/start",
    "/approvals/decide",
    "/patch-proposals/generate",
    "/patch-proposals/decide",
    "/change-snapshots/restore",
    "/automation/",
]


def test_no_public_or_callable_level1_execution_routes_or_client_calls() -> None:
    contents = {f: Path(f).read_text(encoding="utf-8").lower() for f in SCAN_FILES}

    # global: never expose direct level1 execute aliases anywhere in scanned surfaces
    for marker in ["/api/atlas/level1/execute", "/api/atlas/execute"]:
        for path, text in contents.items():
            assert marker not in text, f"forbidden marker '{marker}' found in {path}"

    # client + boot surfaces: must not wire new execution/readiness mutation routes
    for path in ["app/server.py", "main.py", "web/atlas-next/src/api/atlasClient.ts"]:
        text = contents[path]
        for marker in FORBIDDEN_ROUTE_MARKERS:
            assert marker not in text, f"forbidden marker '{marker}' found in {path}"
