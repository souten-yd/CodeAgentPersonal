# Atlas Patch Generation — Decomposition & Large-File Maintainability Design

Status: design + roadmap. Authored 2026-06-24 after a controlled evaluation showed a weak local model
(Qwen3.6-35B, 32K ctx) cannot reliably edit a single plan item that targets **two large files**
(`step_4`: game.js 9 KB + main.js 21 KB → 0/4 success, both with and without input slicing — the
failures are weak-model variance editing a 21 KB file, NOT a context problem).

## Problem
A plan item with several large target files is an **atomic** unit — generated and applied all-or-
nothing. The work unit is too big for a weak model, and a single failed file fails the whole item even
when the others succeeded.

Three axes: (1) **granularity of the work unit** (the plan item), (2) **atomicity of execution**
(all-or-nothing vs partial), (3) **edit method for existing files** (full rewrite vs surgical/region).

## Options
- **(A) Per-file items — split the PLAN.** Planner / decomposition emits one item per file. Each item
  generate→apply→verify→retry independently. Most maintainable: smallest blast radius, independent
  retry, per-file review/rollback, a failed file never blocks others. Cross-file consistency is held
  by the shared `app_interface_contract`; dependency order (define before use) must be respected.
- **(B) Per-file patches — split EXECUTION, keep the item.** The logical "feature" stays one item, but
  each file is generated + applied + verified independently with partial success + per-file retry.
  Lower friction (no planner change); directly salvages the files that succeed. Needs a per-file item
  state model (some files applied, some pending).
- **(C) Huge single file.** Not a multi-file problem — a size problem. Answer: surgical anchored edits
  + Twin region localisation + input slicing (already implemented: PR #2057 surgical/anchors, #2059
  slicing). Edit only the relevant region; the rest is untouched; verify the region/related tests.

## Recommended architecture (4 layers, stacked)
1. **Plan layer** — prefer 1-file / 1-concern items. Use the existing `decomposition_policy`
   (tier / prefer_split / max_source_files) to split large multi-file items into per-file items for
   weak tiers, ordered by dependency.
2. **Execution layer** — per-file apply/verify/retry with **partial success**; never all-or-nothing.
3. **Edit layer** — minimal surgical anchored diffs; for huge files, slice input + region-localise.
4. **Consistency layer** — shared interface contract + TwinProof (tests retained, rerun on change).

## Maintainability principles
Small single-responsibility changes · surgical/anchored/minimal diffs (reviewable, non-destructive) ·
independent verification per unit · retained tests + staleness tracking (TwinProof) · stable contracts
so units compose.

## Roadmap
1. **(B) per-file partial commit + independent retry** — contained, directly improves multi-file
   items; apply the files that pass, surface/retry the ones that fail. **← next.**
2. **(A) per-file (and, for huge files, per-symbol) items at the planner/decomposition** — the larger
   reliability + maintainability win.
3. (C) already largely in place; extend Twin symbol/dependency localisation for huge single files.

Note: no amount of retry/slicing fixes a task that is deterministically too hard for the model
(main.js failed 4/4 at attempt 2 = identical output, early-stopped). The real lever is **smaller
tasks** (A/B) or a stronger model — not more context or more retries.
