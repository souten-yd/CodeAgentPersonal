# Atlas Portal + Model Forge — Master Goal

## Purpose

Build Atlas Portal + Model Forge as a production-grade, evidence-driven model and artifact lifecycle system for KasaneCore.

Portal is the user-facing runtime and artifact lifecycle surface: run generated applications, inspect previews/logs, save or discard run data, snapshot useful state, and package verified work into Capsules.

Model Forge is the model orchestration replacement track: measure local and external models, compare model/route candidates in Arena, maintain model skill profiles, select models by stage and route, and feed real Portal outcomes back into model profiles.

This program supersedes a simple model orchestrator. The legacy model execution path must not be deleted first. It must be wrapped as a Legacy Executor, used for shadow parity and fallback, and retired only after evidence gates pass.

## Current baseline

- Portal / Play / Capsule PR-PPC-0 through PR-PPC-12 are complete.
- Portal UI reconciliation exists: top-level Portal nav, mobile Portal tab, Portal catalog/run sheet, Save/Snapshot/Discard, Export, Fork to Atlas, Uninstall, Delete Data, and Capsule builder dialog.
- Known Portal polish gaps remain: browser upload import, snapshot-list/start-from-snapshot selector, legacy package manifest repair, and Forge trace UX.
- Project Intelligence is in PIR-15. PIR-14 acceptance is complete; PIR-15 final active benchmark, active rollout, and legacy retirement remain incomplete.
- Forge work must inherit PIR discipline: truthful evidence, real execution where required, unavailable is not passed, and no production-complete claims from adapter-only tests or manually supplied metrics.

## Product goal

Create a modern, simple, visually polished UI centered on two user-facing surfaces:

```text
Portal: Run, inspect, save/discard/snapshot, package, replay.
Forge: Select, evaluate, rank, route, and govern models.
```

The user should not need to understand every internal route. The default UI should expose:

- Source Mode: Local Only, Local Preferred, Hybrid, Frontier Preferred, Frontier Only.
- Active Loadout: Local Safe, Local Fast, Local Deep, Hybrid Balanced, OpenRouter Review, Greenfield Builder, Repair Specialist.
- Skill Radar: model strengths and weaknesses by role and task family.
- Arena: optional model/route comparison for selected presets.
- Stage Matrix: advanced, collapsible model selection by stage.
- Route Matrix: advanced, collapsible routing by change class.
- Portal Trace: which model/route/preset produced a runnable artifact and how it performed.

## Definitions

### Portal

Portal owns execution and artifact lifecycle:

- run generated applications through structured launch adapters only;
- serve previews through session-owned gateway/proxy/static serving;
- display logs and runtime state;
- manage generated data as ephemeral, saved, snapshotted, discarded, or capsule data;
- create, import, export, run, fork, uninstall, and data-manage Capsules;
- record execution evidence for verification and Forge feedback.

Portal does not own autonomous code mutation, arbitrary shell execution, PlanPool authority, or Safe Apply.

### Capsule

A Capsule is an immutable package produced from a verified project/profile. Package export remains data-free unless a future explicit, reviewed data-export feature is created. Runtime data remains managed separately by Portal lifecycle rules.

### Forge

Forge owns provider/model selection and evidence-driven routing:

- provider registry: local, self-hosted, OpenAI-compatible, OpenRouter, legacy Atlas;
- model registry and model descriptors;
- model profile store with versioned measurements;
- benchmark presets and tasks;
- Arena runs across model x route x task;
- candidate evaluation with mechanical tests first;
- stage-specific model selection;
- route-specific model selection;
- profile updates from Arena, Atlas verification, and Portal outcomes;
- safe rollout from shadow to primary to legacy retirement.

Forge does not bypass Safe Apply, Portal runtime policy, or Project Intelligence gates.

### Legacy Executor

The current model execution/orchestration path becomes a Legacy Executor Provider under Forge. It remains the default primary path until stage-specific cutover evidence proves Forge is equivalent or superior.

## Source modes

Forge must support these modes:

```text
Local Only         - no external model calls; local/self-hosted providers only.
Local Preferred    - local primary; external fallback only if policy/stage allows.
Hybrid             - stage and route may select local or external models by policy.
Frontier Preferred - external models may be primary for allowed stages.
Frontier Only      - test/comparison mode; not default for private work.
```

Every external provider call must honor stage privacy:

```text
no_external_code
symbol_summary_only
redacted_only
full_source_allowed
```

Default for code-bearing stages is no external code unless the user explicitly changes the policy.

## OpenRouter goal

OpenRouter is implemented as a Forge Provider, not a special hard-coded execution path.

Requirements:

- disabled by default;
- credentials read from environment only;
- secrets never persisted or logged;
- model catalog cache with offline fallback;
- mock-first tests in CI;
- optional live smoke only when explicit environment flags and API key are present;
- provider routing policy translated from Forge privacy/cost/latency/data policy;
- unavailable catalog/API state recorded as unavailable, not passed.

Implementation notes:

- OpenRouter supports a unified API through `/api/v1/chat/completions` and model listing through `GET /api/v1/models`.
- OpenRouter can also be used through the OpenAI SDK with `baseURL = https://openrouter.ai/api/v1`.
- Forge must wrap these details behind `OpenRouterProvider`; callers must not directly hard-code OpenRouter requests outside the provider.

## Benchmark presets

Forge must include selectable presets. Do not force all presets every time.

Initial presets:

```text
Quick
Web App
Repair
Greenfield
```

Expansion presets:

```text
Game / Canvas
UI / Visual
API / Backend
DB / Persistence
Refactor
Multi-file
Custom
```

Depth choices:

```text
Quick       3-5 tasks
Standard    10-20 tasks
Deep        50+ tasks
Full        all selected presets
```

Each preset must declare tasks, risk level, required evaluators, expected runtime budget, applicable routes, and profile dimensions it updates.

## Model and route optimization

Forge must learn both:

- which model is best for a stage/task category;
- which route is best for that model and category.

Examples:

```text
Model A: patch generation champion.
Model B: failure classification champion.
Model C: conservative reviewer.
Model D: UI/Game specialist.
Route X: patch_dsl best for one model.
Route Y: skeleton_fill best for another.
```

Routing is based on:

```text
change magnitude
risk level
task category
stage
model skill profile
route score
privacy policy
cost/latency budget
verification availability
Portal execution outcomes
```

## Portal x Forge integration goal

Portal and Forge connect through evidence and traceability:

- Portal Run stores Forge metadata: provider, model, route, stage policy, loadout, preset, Arena run, candidate, score, privacy mode, cost, latency.
- Portal preview/logs/runtime results feed Candidate Evaluator and Model Profile Store.
- Capsule manifest records Forge trace metadata without mutating package archives after build.
- Capsule replay can re-run and re-score model/route/preset outcomes.
- Portal UI shows a compact Forge Trace panel, with advanced details collapsible.

Portal is not a model selector. Forge is not a runtime. The connection is provenance, evidence, and feedback.

## Non-negotiable gates

A package cannot be `acceptance_complete` unless required gates pass at their proper proof level.

- Component tests prove only component behavior.
- Adapter-only tests do not prove production integration.
- Mock provider tests do not prove live provider behavior.
- Synthetic candidate scores do not prove real model quality.
- Portal UI existence does not prove Portal runtime behavior.
- Arena candidate generation does not apply code directly.
- Candidate adoption must go through Safe Apply and Verification.
- Unavailable is not passed.
- External model calls must be policy-gated and auditable.
- Legacy path retirement requires shadow parity/superiority, rollback, real benchmark, and consumer-zero evidence.

## Completion definition

This program is complete only when:

1. Portal polish gaps are closed or explicitly accepted as deferred with truthful evidence.
2. Forge schemas, providers, registry, profiles, presets, Arena, evaluator, stage matrix, route matrix, and UI are implemented.
3. OpenRouter provider works in mock CI and optional live smoke mode without leaking secrets.
4. Local provider and Legacy Executor paths are integrated under Forge.
5. Portal Run and Capsule metadata include Forge trace.
6. Portal execution outcomes update Forge model profiles.
7. At least Quick, Web App, Repair, and Greenfield presets run end-to-end using real local or configured model execution.
8. At least one Portal-generated runnable artifact is evaluated, run, data-managed, Capsule-packaged, replayed, and fed back into Forge profile scoring.
9. Stage-level shadow evidence exists for patch_generation, test_generation, failure_classification, and repair.
10. Any stage cut over from Legacy to Forge has rollback and documented evidence.
11. UI is modern, mobile-friendly, simple by default, and advanced controls are collapsible.
12. AGENTS.md and current status docs select the active package and contain exact execution evidence.

## Out of scope for initial completion

- Free-form command execution.
- Exporting runtime data inside Capsule package ZIPs.
- Retiring all legacy model paths before evidence gates.
- Making external cloud models mandatory.
- Claiming Runpod/OpenRouter live evidence when not executed.
