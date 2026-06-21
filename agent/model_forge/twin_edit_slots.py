"""Resolve bounded edit slots without asking the model to select anchors."""
from __future__ import annotations

import ast
import re
from pathlib import Path

from pydantic import Field

from agent.model_forge.schema import ForgeModel


class TwinEditSlot(ForgeModel):
    slot_id: str = Field(min_length=1)
    file: str = Field(min_length=1)
    symbol_ref: str = ""
    operation: str
    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)
    anchor_text: str = ""
    anchor_occurrences: int = Field(default=0, ge=0)
    max_new_lines: int = Field(default=80, ge=1)
    required_behavior: str = ""
    forbidden_behavior: list[str] = Field(default_factory=list)
    required_tests: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence_refs: list[str] = Field(default_factory=list)


class TwinEditSlotResolver:
    def __init__(self, quality_gate=None) -> None:
        if quality_gate is None:
            from agent.model_forge.twin_slot_quality import TwinSlotQualityGate
            quality_gate = TwinSlotQualityGate()
        self.quality_gate = quality_gate

    def resolve(
        self, *, project_root: str | Path, target_file: str, goal: str,
        expected_symbols: list[str] | None = None, required_tests: list[str] | None = None,
        forbidden_refs: list[str] | None = None,
    ) -> TwinEditSlot | None:
        root = Path(project_root).resolve()
        path = (root / target_file).resolve()
        if root not in path.parents or not path.is_file():
            return None
        content = path.read_text(encoding="utf-8")
        symbols = expected_symbols or self._goal_tokens(goal)
        if path.suffix == ".py":
            found = self._python_symbol(content, symbols)
            if found:
                name, start, end, anchor = found
                occurrences = content.count(anchor)
                slot = TwinEditSlot(
                    slot_id=f"slot:{target_file}:{name}", file=target_file,
                    symbol_ref=name, operation="replace_symbol_body", start_line=start,
                    end_line=end, anchor_text=anchor if occurrences == 1 else "",
                    anchor_occurrences=occurrences, required_behavior=goal,
                    required_tests=required_tests or [], confidence=0.95 if occurrences == 1 else 0.65,
                    evidence_refs=[f"ast:{target_file}:{start}-{end}"],
                )
                return slot if self.quality_gate.evaluate(slot=slot, project_root=root, forbidden_refs=forbidden_refs).accepted else None
        anchor = self._unique_insertion_anchor(content)
        if not anchor:
            return None
        line = content[:content.index(anchor)].count("\n") + 1
        slot = TwinEditSlot(
            slot_id=f"slot:{target_file}:insertion", file=target_file,
            operation="insert_after", start_line=line, end_line=line,
            anchor_text=anchor, anchor_occurrences=1, required_behavior=goal,
            required_tests=required_tests or [], confidence=0.75,
            evidence_refs=[f"unique_anchor:{target_file}:{line}"],
        )
        return slot if self.quality_gate.evaluate(slot=slot, project_root=root, forbidden_refs=forbidden_refs).accepted else None

    @staticmethod
    def _python_symbol(content: str, symbols: list[str]):
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return None
        wanted = {item.split(":")[-1].split(".")[-1].lower() for item in symbols}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name.lower() in wanted:
                line = content.splitlines()[node.lineno - 1]
                return node.name, node.lineno, int(node.end_lineno or node.lineno), line
        return None

    @staticmethod
    def _goal_tokens(goal: str) -> list[str]:
        return re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", goal)

    @staticmethod
    def _unique_insertion_anchor(content: str) -> str:
        candidates = [line for line in content.splitlines() if line.strip().startswith(("# UNIQUE_", "// UNIQUE_"))]
        return candidates[0] if len(candidates) == 1 and content.count(candidates[0]) == 1 else ""
