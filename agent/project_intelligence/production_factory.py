"""Production Project Intelligence composition root (PIR-2)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent.architecture_blueprint.facade import DisabledArchitectureBlueprintModule
from agent.architecture_blueprint.module import ArchitectureBlueprintModuleImpl
from agent.architecture_blueprint.store import BlueprintStore
from agent.project_convergence.facade import DisabledConvergenceModule
from agent.project_convergence.module import ConvergenceModuleImpl
from agent.project_convergence.store import ConvergenceStore
from agent.project_intelligence.coordinator import ProjectIntelligenceCoordinator
from agent.project_intelligence.factory import build_project_intelligence
from agent.project_intelligence.rollout import RolloutConfig
from agent.project_twin.facade import DisabledDigitalTwinModule
from agent.project_twin.module import DigitalTwinModuleImpl


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class ProductionProjectIntelligenceService:
    """App-lifecycle holder for the production coordinator and concrete modules."""

    coordinator: ProjectIntelligenceCoordinator
    data_dir: Path
    rollout: RolloutConfig
    module_paths: dict[str, Path]
    rollout_state_path: Path

    def close(self) -> None:
        for value in (
            getattr(self.coordinator, "_twin", None),
            getattr(self.coordinator, "_blueprint", None),
            getattr(self.coordinator, "_convergence", None),
        ):
            close = getattr(value, "close", None)
            if callable(close):
                close()

    def implementation_classes(self) -> dict[str, str]:
        return {
            "digital_twin": type(getattr(self.coordinator, "_twin", None)).__name__,
            "blueprint": type(getattr(self.coordinator, "_blueprint", None)).__name__,
            "convergence": type(getattr(self.coordinator, "_convergence", None)).__name__,
        }

    def preflight(self) -> dict[str, Any]:
        classes = self.implementation_classes()
        mode = self.rollout.mode()
        disabled = {name: cls for name, cls in classes.items() if cls.startswith("Disabled")}
        store_paths = {name: str(path) for name, path in self.module_paths.items()}
        corrupt = [name for name, path in self.module_paths.items() if path.exists() and path.is_dir()]
        ok = mode == "off" or (not disabled and not corrupt)
        reasons: list[str] = []
        if mode != "off" and disabled:
            reasons.append("disabled_required_module")
        if corrupt:
            reasons.append("store_path_unusable")
        return {
            "ok": ok,
            "mode": mode,
            "active_phases": sorted(self.rollout.active_phases),
            "shadow": self.rollout.shadow,
            "implementation_classes": classes,
            "disabled_modules": disabled,
            "store_paths": store_paths,
            "reasons": reasons,
        }

    def health(self) -> dict[str, Any]:
        state = _read_rollout_state(self.rollout_state_path)
        return {
            "status": "ok" if self.preflight()["ok"] else "blocked",
            "data_dir": str(self.data_dir),
            "rollout": {
                "mode": self.rollout.mode(),
                "enabled": self.rollout.enabled,
                "shadow": self.rollout.shadow,
                "active_phases": sorted(self.rollout.active_phases),
            },
            "preflight": self.preflight(),
            "rollout_state": state,
        }


def _read_rollout_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"transitions": [], "rollback_history": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"transitions": [], "rollback_history": [], "read_error": True}


def _write_rollout_state(path: Path, *, rollout: RolloutConfig, preflight: dict[str, Any]) -> None:
    prior = _read_rollout_state(path)
    transitions = list(prior.get("transitions") or [])
    transitions.append(
        {
            "recorded_at": _now(),
            "mode": rollout.mode(),
            "active_phases": sorted(rollout.active_phases),
            "preflight_ok": bool(preflight.get("ok")),
        }
    )
    payload = {
        "current_mode": rollout.mode(),
        "active_phases": sorted(rollout.active_phases),
        "last_preflight_ok": bool(preflight.get("ok")),
        "transitions": transitions[-50:],
        "rollback_history": list(prior.get("rollback_history") or []),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_production_project_intelligence(
    *,
    ca_data_dir: str | Path,
    rollout: RolloutConfig | None = None,
    env: dict | None = None,
) -> ProductionProjectIntelligenceService:
    """Construct the production service once for app lifecycle registration."""
    config = rollout if rollout is not None else RolloutConfig.from_env(env)
    data_dir = Path(ca_data_dir).expanduser().resolve() / "project_intelligence"
    data_dir.mkdir(parents=True, exist_ok=True)
    module_paths = {
        "digital_twin": data_dir / "digital_twin.sqlite3",
        "blueprint": data_dir / "blueprint.sqlite3",
        "convergence": data_dir / "convergence.sqlite3",
    }

    if config.mode() == "off":
        coordinator = build_project_intelligence(
            rollout=config,
            digital_twin=DisabledDigitalTwinModule(),
            blueprint=DisabledArchitectureBlueprintModule(),
            convergence=DisabledConvergenceModule(),
        )
    else:
        coordinator = build_project_intelligence(
            rollout=config,
            digital_twin=DigitalTwinModuleImpl(module_paths["digital_twin"]),
            blueprint=ArchitectureBlueprintModuleImpl(BlueprintStore(module_paths["blueprint"])),
            convergence=ConvergenceModuleImpl(store=ConvergenceStore(module_paths["convergence"])),
        )

    service = ProductionProjectIntelligenceService(
        coordinator=coordinator,
        data_dir=data_dir,
        rollout=config,
        module_paths=module_paths,
        rollout_state_path=data_dir / "rollout_state.json",
    )
    preflight = service.preflight()
    _write_rollout_state(service.rollout_state_path, rollout=config, preflight=preflight)
    if config.mode() != "off" and not preflight["ok"]:
        service.close()
        raise RuntimeError(f"project intelligence preflight failed: {preflight['reasons']}")
    return service

