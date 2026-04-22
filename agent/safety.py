from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

RiskType = Literal["destructive_change", "bulk_dependency_addition", "production_impact"]
StopType = Literal["iteration_limit", "stagnation", "evaluation_regression", "budget_exhausted"]


@dataclass(slots=True)
class HumanGateDecision:
    """人間確認が必要かどうかの判定結果。"""

    required: bool
    reasons: list[str] = field(default_factory=list)
    risk_type: RiskType | None = None
    prompt: str = ""


@dataclass(slots=True)
class AutoStopDecision:
    """自動停止判定と UI 通知用メッセージ。"""

    should_stop: bool
    stop_type: StopType | None = None
    reason: str = ""
    ui_notice: str = ""


def detect_human_gate(action: Any) -> HumanGateDecision:
    """破壊的変更 / 依存大量追加 / 本番影響を検知して確認要求を返す。"""
    tool = str(getattr(action, "tool", "") or (action.get("tool") if isinstance(action, dict) else "")).lower()
    payload = action.input if hasattr(action, "input") else (action.get("input", {}) if isinstance(action, dict) else {})
    text = f"{tool}\n{payload}".lower()

    destructive_keywords = ("rm -rf", "drop table", "truncate", "delete ", "force push", "reset --hard")
    dependency_keywords = ("pip install", "poetry add", "npm install", "pnpm add", "cargo add")
    production_keywords = ("prod", "production", "deploy", "kubectl", "terraform apply", "migration")

    if any(k in text for k in destructive_keywords):
        return HumanGateDecision(
            required=True,
            reasons=["破壊的変更の可能性を検知"],
            risk_type="destructive_change",
            prompt="この操作は破壊的変更の可能性があります。実行を続行しますか？",
        )

    if any(k in text for k in dependency_keywords):
        dependency_list = payload.get("packages") if isinstance(payload, dict) else None
        dependency_count = len(dependency_list) if isinstance(dependency_list, list) else 0
        if dependency_count >= 10 or "requirements" in text:
            return HumanGateDecision(
                required=True,
                reasons=["依存の大量追加を検知"],
                risk_type="bulk_dependency_addition",
                prompt="多数の依存関係を追加しようとしています。確認後に続行しますか？",
            )

    if any(k in text for k in production_keywords):
        return HumanGateDecision(
            required=True,
            reasons=["本番影響操作の可能性を検知"],
            risk_type="production_impact",
            prompt="本番環境に影響する可能性があります。確認後に続行しますか？",
        )

    return HumanGateDecision(required=False)


def build_autostop_notice(decision: AutoStopDecision) -> str:
    if not decision.should_stop:
        return ""
    return decision.ui_notice or f"自動停止: {decision.reason}"
