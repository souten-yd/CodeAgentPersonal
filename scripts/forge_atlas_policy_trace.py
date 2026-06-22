"""Atlas planner -> codegen policy trace: what the autonomous orchestrator actually decides.

The orchestrator drives goal -> plan -> generate -> verify -> self-correct, and at generation time
it calls resolve_atlas_generation_policy (-> ExecutionPolicySelector) to pick route / method / Twin
injection, then escalates on failure. This script traces that real decision for representative model
profiles and across consecutive failures, so the integrated features are visible engaging together:

  - capability-driven method + injection
  - method substitution (weak edit/structured -> deterministic/anchor/slot)
  - Twin-offload rescue (weak impact/contract/test -> BlastMap/ContractSentinel/TwinProof forced)
  - unmeasured -> conservative injection
  - failure escalation (+injection, then review-only)

Deterministic (no model needed). Run:  python scripts/forge_atlas_policy_trace.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.model_forge.execution_policy import ExecutionPolicySelector, ModelCapabilityProfile
from agent.model_forge.route_matrix import ChangeClass
from agent.twin_control_plane.contracts import ModelCapabilityMode

_SEL = ExecutionPolicySelector()
_KEY_REASONS = ("injection=", "unmeasured", "injection_sweep", "twin_assist_injection",
                "failure_escalation", "method_substitution", "twin_rescue", "capability_rescue",
                "repeated_failure")


def trace(tag, profile, *, change=ChangeClass.MEDIUM, task="bugfix", failures=(0, 1, 2)):
    print(f"\n### {tag}")
    for f in failures:
        p = _SEL.select(change, task_category=task, model_profile=profile, consecutive_method_failures=f)
        reasons = [r for r in p.reasons if any(k in r for k in _KEY_REASONS)]
        print(f"  failures={f}: route={p.route.value} method={p.method_variant.value} "
              f"injection={int(p.twin_injection_level)}")
        print(f"     modules={p.required_twin_modules}")
        print(f"     reasons={reasons}")


if __name__ == "__main__":
    trace("Unmeasured model (no benchmark yet)", ModelCapabilityProfile(model_id="unknown"))

    trace("Weak local: bad at edit_intent + structured (method substitution)",
          ModelCapabilityProfile(
              model_id="weak", mode=ModelCapabilityMode.WEAK_LOCAL,
              capability_scores={"structured_output_fidelity": 0.2, "edit_intent_quality": 0.2,
                                 "anchor_selection_quality": 0.9},
              known_weaknesses=["structured_output_fidelity", "edit_intent_quality"],
              measured_optimal_injection_level=0, injection_objective="min_sufficient"))

    trace("Weak reasoning: bad at impact/contract/test (Twin-offload rescue)",
          ModelCapabilityProfile(
              model_id="reasoner", mode=ModelCapabilityMode.WEAK_LOCAL,
              capability_scores={"impact_analysis": 0.2, "contract_preservation": 0.2,
                                 "test_generation": 0.2},
              known_weaknesses=["impact_analysis", "contract_preservation", "test_generation"]))

    trace("Strong model (measured optimal = minimal injection)",
          ModelCapabilityProfile(
              model_id="strong", mode=ModelCapabilityMode.STANDARD,
              capability_scores={d: 0.9 for d in (
                  "structured_output_fidelity", "edit_intent_quality", "anchor_selection_quality",
                  "impact_analysis", "contract_preservation", "test_generation")},
              measured_optimal_injection_level=0, injection_objective="min_sufficient"))
