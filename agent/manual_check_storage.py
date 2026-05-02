from __future__ import annotations

import json
from pathlib import Path

from agent.manual_check_schema import ManualLLMCheckResult


class ManualCheckStorage:
    def __init__(self, ca_data_dir: str | Path) -> None:
        self.base_dir = Path(ca_data_dir)

    def _checks_dir(self, run_id: str) -> Path:
        p = self.base_dir / "runs" / run_id / "manual_checks"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def save_manual_check(self, record: ManualLLMCheckResult) -> None:
        cd = self._checks_dir(record.run_id)
        (cd / f"{record.check_id}.manual_check.json").write_text(json.dumps(record.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
        (cd / f"{record.check_id}.manual_check.md").write_text(self._to_markdown(record), encoding="utf-8")

    def load_manual_check(self, run_id: str, check_id: str) -> dict:
        path = self._checks_dir(run_id) / f"{check_id}.manual_check.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def list_manual_checks(self, run_id: str) -> list[dict]:
        cd = self._checks_dir(run_id)
        out: list[dict] = []
        for path in sorted(cd.glob("*.manual_check.json")):
            out.append(json.loads(path.read_text(encoding="utf-8")))
        return out

    def _to_markdown(self, record: ManualLLMCheckResult) -> str:
        return (
            f"# Manual Check {record.check_id}\n\n"
            f"- run_id: {record.run_id}\n"
            f"- patch_id: {record.patch_id}\n"
            f"- reviewer: {record.reviewer}\n"
            f"- model: {record.model}\n"
            f"- apply_allowed: {record.apply_allowed}\n"
            f"- quality_score: {record.quality_score}\n"
            f"- verification_status: {record.verification_status}\n"
            f"- observed_issue: {record.observed_issue}\n"
            f"- notes: {record.notes}\n"
        )
