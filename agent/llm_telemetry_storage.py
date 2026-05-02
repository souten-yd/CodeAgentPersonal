from __future__ import annotations

import json
from pathlib import Path

from agent.llm_telemetry_schema import LLMCallTelemetry


class LLMTelemetryStorage:
    def __init__(self, ca_data_dir: str | Path) -> None:
        self.base_dir = Path(ca_data_dir)

    def _telemetry_dir(self, run_id: str) -> Path:
        p = self.base_dir / "runs" / run_id / "llm_telemetry"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def save_telemetry(self, record: LLMCallTelemetry) -> None:
        td = self._telemetry_dir(record.run_id)
        (td / f"{record.telemetry_id}.llm.json").write_text(json.dumps(record.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
        (td / f"{record.telemetry_id}.llm.md").write_text(self._telemetry_to_markdown(record), encoding="utf-8")

    def load_telemetry(self, run_id: str, telemetry_id: str) -> dict:
        path = self._telemetry_dir(run_id) / f"{telemetry_id}.llm.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def list_telemetry(self, run_id: str) -> list[dict]:
        td = self._telemetry_dir(run_id)
        out: list[dict] = []
        for path in sorted(td.glob("*.llm.json")):
            out.append(json.loads(path.read_text(encoding="utf-8")))
        return out

    def _telemetry_to_markdown(self, record: LLMCallTelemetry) -> str:
        return (
            f"# LLM Telemetry {record.telemetry_id}\n\n"
            f"- purpose: {record.purpose}\n"
            f"- run_id: {record.run_id}\n"
            f"- patch_id: {record.patch_id}\n"
            f"- success: {record.success}\n"
            f"- duration_ms: {record.duration_ms}\n"
            f"- model: {record.model}\n"
            f"- validation_reason: {record.validation_reason}\n"
            f"- apply_allowed_after_validation: {record.apply_allowed_after_validation}\n"
        )
