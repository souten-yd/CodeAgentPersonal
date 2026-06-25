# KasaneCore Agent Entry Point

This file is a compatibility entrypoint for agents that look for `Agent.md` instead of `AGENTS.md`.

For the authoritative root instructions, read:

```text
AGENTS.md
```

## Current Codex package

For the next weak-LLM / Atlas hardening work, start from:

```text
docs/generic_weak_llm_app_hardening_plan.md
```

Then read the completed base plan:

```text
docs/weak_llm_large_file_edit_hardening_plan.md
```

## Goal

Continue from the completed weak-LLM large-file edit safety work and generalize it for games, Web apps, and business applications.

The core rule is:

```text
weak model chooses or describes the smallest edit
Atlas normalizes and dry-runs it in memory
validators inspect the post-apply file state
known violations may be repaired only by deterministic recipes
Safe Apply remains the only authority that changes files
```

Do not add new game-only top-level special cases. WebGL/Canvas repair should become one domain recipe under a generic repair/contract framework.

## Package status

Use `docs/generic_weak_llm_app_hardening_plan.md` for completion evidence and any follow-up work:

1. GA1 — Post-Apply Preview for generic validation: done
2. GA2 — Harden sliced-content salvage: done
3. GA3 — Generic Contract Registry: done
4. GA4 — Repair Recipe Registry: done
5. GA5 — File-type-aware edit policy and primitives: done
6. GA6 — Generic validators after preview: done
7. GA7 — 8080 weak-model generic live checks: done
8. GA8 — Documentation and agent workflow update: done

Preserve all rules in `AGENTS.md`: no bypass around Proposal / Safe Apply / Verification, no remote publication without approval, unavailable is not passed, and mock output is not live evidence.
