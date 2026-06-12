"""Generate the Forge legacy model-execution consumer registry (PFG-37).

Scans agent/ and app/ for direct callers of the legacy model-execution path and writes a
registry JSON plus a retirement-gate evaluation. Read-only; never deletes anything.

Usage:
    python tools/generate_forge_model_consumer_registry.py --root . \
        --output docs/generated/forge_model_consumer_registry.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.model_forge.retirement import (
    build_model_consumer_registry,
    evaluate_model_retirement_gate,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", default="docs/generated/forge_model_consumer_registry.json")
    parser.add_argument("--benchmark-passed", action="store_true")
    parser.add_argument("--shadow-passed", action="store_true")
    parser.add_argument("--rollback-available", action="store_true")
    args = parser.parse_args()

    registry = build_model_consumer_registry(args.root)
    gate = evaluate_model_retirement_gate(
        registry,
        benchmark_passed=args.benchmark_passed,
        shadow_passed=args.shadow_passed,
        rollback_available=args.rollback_available,
    )
    payload = {"registry": registry.model_dump(mode="json"), "retirement_gate": gate.model_dump(mode="json")}
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"legacy_consumer_count={registry.legacy_consumer_count} "
          f"retirement_allowed={gate.allowed} blocked={gate.blocked_reasons}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
