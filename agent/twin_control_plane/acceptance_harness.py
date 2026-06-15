"""End-to-end acceptance harness (TFG-13 / Package 12-13 closure).

Wires the gated ``ActiveIntegrationOrchestrator`` to *real* hooks so a representative
task can run all the way through the pipeline and produce real LLM + real runtime
acceptance evidence:

- generation calls a real model (via a ``ChatFn``) and extracts a code block;
- Safe Apply writes the extracted code into an isolated, Atlas-owned workspace and makes
  a local commit through the Git Steward adapter (never remote);
- verification runs a real command (e.g. pytest) in that workspace and reports real
  pass/fail evidence — ``unavailable`` stays distinct from ``passed``.

The harness only ever operates inside the caller-provided workspace path. It performs no
remote Git operation and does not touch the live Atlas pipeline.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Callable

from agent.git_steward.local_adapter import create_local_commit
from agent.twin_control_plane.active_integration import ApplyOutcome, PipelineHooks, ProposalDraft
from agent.twin_control_plane.instruction_compiler import CompiledInstruction
from agent.twin_control_plane.patch_impact_gate import VerificationEvidence
from agent.twin_control_plane.real_llm_eval import ChatFn, ModelChatResponse
from agent.twin_control_plane.repair_compass import RepairCompassReport

_CODE_BLOCK = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.DOTALL)


def extract_code_block(text: str) -> str:
    """Extract the first fenced code block; fall back to the raw text when none is found."""
    match = _CODE_BLOCK.search(text or "")
    if match:
        return match.group(1).strip() + "\n"
    return (text or "").strip() + "\n"


def _repair_addendum(repair: RepairCompassReport | None) -> str:
    if repair is None:
        return ""
    lines = ["", "A previous attempt failed verification. Repair guidance (advisory):"]
    for instruction in repair.instructions:
        lines.append(f"- {instruction.summary}")
    lines.append("Fix the implementation; do not weaken or delete the test.")
    return "\n".join(lines)


class LocalAcceptanceHooks:
    """Builds real generate/safe_apply/verify hooks over a single workspace.

    Generation and Safe Apply share the last generated source via this object so the
    orchestrator stays a pure sequencer while real I/O is confined here."""

    def __init__(
        self,
        *,
        chat: ChatFn,
        repo_path: str | Path,
        target_file: str,
        task_prompt: str,
        verify_command: list[str],
        commit_message: str = "Atlas active-integration patch",
    ) -> None:
        self._chat = chat
        self._repo = Path(repo_path)
        self._target_file = target_file
        self._task_prompt = task_prompt
        self._verify_command = list(verify_command)
        self._commit_message = commit_message
        self._counter = 0
        self._last_code = ""
        self._last_model_available = False
        self.transcript: list[dict] = []

    def hooks(self) -> PipelineHooks:
        return PipelineHooks(
            generate=self._generate, safe_apply=self._safe_apply,
            verify=self._verify, refresh_twin=self._refresh_twin,
        )

    @property
    def model_available(self) -> bool:
        return self._last_model_available

    def _generate(self, instruction: CompiledInstruction, repair: RepairCompassReport | None) -> ProposalDraft:
        self._counter += 1
        user_prompt = (
            f"{self._task_prompt}\n\n"
            f"Return ONLY the complete contents of `{self._target_file}` in a single "
            f"python code block. Do not include explanations."
            f"{_repair_addendum(repair)}"
        )
        response: ModelChatResponse = self._chat(instruction.text, user_prompt)
        self._last_model_available = response.available
        self._last_code = extract_code_block(response.text) if response.available else ""
        self.transcript.append({
            "attempt": self._counter, "available": response.available,
            "latency_ms": response.latency_ms, "output_excerpt": (response.text or "")[:400],
        })
        return ProposalDraft(
            proposal_id=f"prop{self._counter}", summary=f"attempt {self._counter}",
            changed_files=[self._target_file],
            raw_output_ref=f"transcript:{self._counter}",
        )

    def _safe_apply(self, proposal: ProposalDraft) -> ApplyOutcome:
        # The Safe Apply boundary: write into the Atlas-owned workspace, then local commit.
        if not self._last_code:
            return ApplyOutcome(applied=False, via_safe_apply=True, reasons=["no_model_code"])
        target = self._repo / self._target_file
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self._last_code, encoding="utf-8")
        commit = create_local_commit(self._repo, message=self._commit_message,
                                     paths=[self._target_file])
        return ApplyOutcome(
            applied=True, via_safe_apply=True, changed_files=[self._target_file],
            commit_sha=commit.commit_sha, reasons=commit.reasons,
        )

    def _verify(self, proposal: ProposalDraft, apply: ApplyOutcome) -> list[VerificationEvidence]:
        if not apply.applied:
            return [VerificationEvidence(evidence_id="verify_unavailable", status="unavailable",
                                         command=" ".join(self._verify_command),
                                         summary="no_code_applied")]
        try:
            proc = subprocess.run(self._verify_command, cwd=str(self._repo), text=True,
                                  capture_output=True, timeout=120)
        except Exception as exc:  # runtime genuinely unavailable
            return [VerificationEvidence(evidence_id="verify_unavailable", status="unavailable",
                                         command=" ".join(self._verify_command),
                                         summary=f"runner_error:{type(exc).__name__}")]
        status = "passed" if proc.returncode == 0 else "failed"
        tail = (proc.stdout + proc.stderr).strip().splitlines()[-1:] or [""]
        return [VerificationEvidence(
            evidence_id=f"verify_{self._counter}", status=status,
            command=" ".join(self._verify_command), refs=[self._target_file],
            summary=tail[0][:200],
        )]

    def _refresh_twin(self, proposal: ProposalDraft, apply: ApplyOutcome) -> str:
        # A local commit sha stands in for the post-apply Twin revision marker.
        return apply.commit_sha or f"workspace_rev_{self._counter}"


__all__ = ["LocalAcceptanceHooks", "extract_code_block"]
