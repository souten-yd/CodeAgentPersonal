from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AtlasTaskVerificationContract:
    contract_id: str
    label: str
    expected_signals: list[str] = field(default_factory=list)
    required_evidence: list[str] = field(default_factory=list)
    repair_instructions: list[str] = field(default_factory=list)

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


_CONTRACTS = {
    "python_module_v1": AtlasTaskVerificationContract(
        contract_id="python_module_v1",
        label="Python module/service",
        required_evidence=["syntax_or_import", "focused_test_when_available"],
        repair_instructions=["Run a focused Python syntax/import check and fix import/runtime errors in the implementation file."],
    ),
    "api_endpoint_v1": AtlasTaskVerificationContract(
        contract_id="api_endpoint_v1",
        label="API endpoint",
        required_evidence=["focused_api_test", "expected_response_signal"],
        repair_instructions=["Verify the endpoint response body/status includes the expected behavior signal; repair the API implementation, not only tests."],
    ),
    "browser_html_ui_v1": AtlasTaskVerificationContract(
        contract_id="browser_html_ui_v1",
        label="Browser HTML/UI",
        required_evidence=["visual_contract", "browser_smoke_or_static_contract"],
        repair_instructions=["Repair DOM/CSS/JS behavior so browser/static visual checks observe the expected UI signal."],
    ),
    "canvas_game_v1": AtlasTaskVerificationContract(
        contract_id="canvas_game_v1",
        label="Canvas/browser game",
        required_evidence=["canvas_frame_change", "core_game_signal"],
        repair_instructions=["Repair the game loop, canvas drawing, and core gameplay signal instead of adding file-existence checks."],
    ),
    "persistence_state_reload_v1": AtlasTaskVerificationContract(
        contract_id="persistence_state_reload_v1",
        label="Persistence/state reload",
        required_evidence=["state_change", "reload_or_restart_signal"],
        repair_instructions=["Verify state survives reload/restart and repair the persistence path if the reload signal is absent."],
    ),
    "multi_file_integration_v1": AtlasTaskVerificationContract(
        contract_id="multi_file_integration_v1",
        label="Multi-file integration",
        required_evidence=["integration_graph", "entrypoint_reaches_changed_files"],
        repair_instructions=["Wire generated modules into the runtime entrypoint; do not leave disconnected artifacts."],
    ),
    "unknown_task_v1": AtlasTaskVerificationContract(
        contract_id="unknown_task_v1",
        label="Unknown task",
        required_evidence=["focused_verification"],
        repair_instructions=["Add a task-specific verification contract before claiming completion."],
    ),
}


_ALIASES = {
    "python": "python_module_v1",
    "python_module": "python_module_v1",
    "service": "python_module_v1",
    "api": "api_endpoint_v1",
    "api_endpoint": "api_endpoint_v1",
    "endpoint": "api_endpoint_v1",
    "browser": "browser_html_ui_v1",
    "html": "browser_html_ui_v1",
    "ui": "browser_html_ui_v1",
    "browser_html": "browser_html_ui_v1",
    "canvas": "canvas_game_v1",
    "game": "canvas_game_v1",
    "canvas_game": "canvas_game_v1",
    "persistence": "persistence_state_reload_v1",
    "state_reload": "persistence_state_reload_v1",
    "reload": "persistence_state_reload_v1",
    "multi_file": "multi_file_integration_v1",
    "integration": "multi_file_integration_v1",
}


def get_task_verification_contract(contract_id: str) -> AtlasTaskVerificationContract | None:
    key = _normalize_contract_id(contract_id)
    return _CONTRACTS.get(key)


def select_task_verification_contract(item, pool) -> AtlasTaskVerificationContract:
    explicit = _explicit_contract_payload(item)
    explicit_id = str(explicit.get("contract_id") or explicit.get("type") or "").strip()
    contract = get_task_verification_contract(explicit_id)
    if contract is not None:
        return _with_expected_signals(contract, explicit)

    target_files = [str(path).lower().replace("\\", "/") for path in (getattr(item, "target_files", []) or [])]
    metadata = getattr(item, "metadata", {}) or {}
    file_changes = metadata.get("file_changes") if isinstance(metadata.get("file_changes"), list) else []
    changed_paths = [str(change.get("path") or "").lower().replace("\\", "/") for change in file_changes if isinstance(change, dict)]
    all_paths = target_files + changed_paths
    text = " ".join([
        str(getattr(item, "title", "") or ""),
        str(getattr(item, "goal", "") or ""),
        " ".join(getattr(item, "done_definition", []) or []),
    ]).lower()

    if _looks_like_canvas_game(text, all_paths):
        return _with_expected_signals(_CONTRACTS["canvas_game_v1"], explicit)
    if any(path.endswith(".html") for path in all_paths) or any(token in text for token in ("browser", "ui", "html", "dom")):
        return _with_expected_signals(_CONTRACTS["browser_html_ui_v1"], explicit)
    if len([path for path in all_paths if path]) > 1:
        return _with_expected_signals(_CONTRACTS["multi_file_integration_v1"], explicit)
    if any(token in text for token in ("api", "endpoint", "response", "route")):
        return _with_expected_signals(_CONTRACTS["api_endpoint_v1"], explicit)
    if any(token in text for token in ("persist", "reload", "restart", "state")):
        return _with_expected_signals(_CONTRACTS["persistence_state_reload_v1"], explicit)
    if any(path.endswith(".py") for path in all_paths):
        return _with_expected_signals(_CONTRACTS["python_module_v1"], explicit)
    return _with_expected_signals(_CONTRACTS["unknown_task_v1"], explicit)


def evaluate_expected_signals(contract: AtlasTaskVerificationContract, *, output_text: str, file_contents: dict[str, str]) -> dict[str, Any]:
    expected = [str(signal).strip() for signal in contract.expected_signals if str(signal).strip()]
    if not expected:
        return {"status": "passed", "expected_signals": [], "matched_signals": [], "missing_signals": []}
    haystack = "\n".join([output_text, *file_contents.values()]).lower()
    matched = [signal for signal in expected if signal.lower() in haystack]
    missing = [signal for signal in expected if signal not in matched]
    return {
        "status": "passed" if not missing else "failed",
        "expected_signals": expected,
        "matched_signals": matched,
        "missing_signals": missing,
    }


def _explicit_contract_payload(item) -> dict[str, Any]:
    metadata = getattr(item, "metadata", {}) or {}
    for candidate in (
        getattr(item, "verification_contract", None),
        metadata.get("verification_contract"),
        metadata.get("task_verification_contract"),
        metadata.get("verification"),
    ):
        if isinstance(candidate, dict) and candidate:
            return dict(candidate)
    return {}


def _with_expected_signals(contract: AtlasTaskVerificationContract, payload: dict[str, Any]) -> AtlasTaskVerificationContract:
    signals = payload.get("expected_signals") or payload.get("signals") or contract.expected_signals
    if isinstance(signals, str):
        signals = [signals]
    if not isinstance(signals, list):
        signals = []
    return AtlasTaskVerificationContract(
        contract_id=contract.contract_id,
        label=contract.label,
        expected_signals=[str(signal).strip() for signal in signals if str(signal).strip()],
        required_evidence=list(contract.required_evidence),
        repair_instructions=list(contract.repair_instructions),
    )


def _normalize_contract_id(value: str) -> str:
    key = str(value or "").strip().lower()
    if key in _CONTRACTS:
        return key
    return _ALIASES.get(key, key)


def _looks_like_canvas_game(text: str, paths: list[str]) -> bool:
    if any(path.endswith(".html") for path in paths) and any(token in text for token in ("game", "score", "player", "canvas")):
        return True
    if any(path.endswith((".js", ".html")) for path in paths) and "canvas" in text:
        return True
    return any(Path(path).stem in {"game", "canvas"} for path in paths)
