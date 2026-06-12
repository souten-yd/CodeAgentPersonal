# Atlas Forge — User Guide

Forge is the Model Forge surface inside Atlas: it picks, scores, and (optionally) routes
models for the Atlas pipeline. It is **off by default** — the legacy model executor stays
primary until you explicitly opt a stage in. Forge never applies a model's output directly;
adoption always goes through Proposal → Safe Apply → Verification.

## Opening Forge

Click the **Forge** tab in the top navigation (between Echo/Nexus and Portal; a Forge tab
also appears on mobile). The default view is intentionally simple.

## Tabs

- **Overview** — Forge on/off, the active loadout, the source mode, profile count, and a
  health card per provider (Legacy Atlas / Local model / OpenRouter). A provider that is
  disabled or missing a key shows a plain status, not an error.
- **Skills** — champion model per skill dimension and a compact per-model score list.
  Click a model to open a detail drawer with all dimension scores. Empty until you run a
  benchmark or Arena.
- **Benchmark** — pick presets (Quick / Web App / Repair / Greenfield, plus more), a depth
  (default *standard*; full/deep is opt-in), and a provider + model. External providers
  show a privacy warning. Run goes through the non-applying Arena path.
- **Arena** — candidate comparison from the last run (contract, latency, route) with a
  mechanical winner. Adoption requires Safe Apply — there is **no direct apply button**.
- **Loadouts** — simple presets (Local Safe/Fast/Deep, Hybrid Balanced, OpenRouter Review,
  Greenfield Builder, Repair Specialist). Applying a loadout updates stage/provider policy;
  a risky loadout (external models or live routing) asks for confirmation first.
- **Advanced** — collapsible Stage Matrix and Route Matrix. Changing a stage to a
  live-routing mode (fixed/auto/arena) requires confirmation; critical change classes are
  flagged. Hidden by default.

## Providers and source modes

- **Local model** — set `FORGE_LOCAL_BASE_URL` (e.g. `http://localhost:8080`) and
  optionally `FORGE_LOCAL_MODEL` to use a local OpenAI-compatible server. Data stays local.
- **OpenRouter** — disabled by default. Set `OPENROUTER_API_KEY` and enable it in policy.
  The API key is read from the environment and is never persisted or logged. External
  providers are blocked under the **Local Only** source mode.
- **Legacy Atlas** — the existing structured-output executor; it remains primary and is the
  fallback when a stage is cut over to Forge.

## Safety model

- Forge is off by default; legacy execution is primary.
- No automatic cutover: promoting a stage to Forge primary needs explicit acknowledgement,
  and a tested **rollback** reverts it to shadow at any time.
- Arena candidates are never applied directly — Proposal → Safe Apply → Verification.
- A missing external key is shown as disabled/unavailable, never claimed as passed.
- Capsule packages stay immutable; Forge trace is a sidecar, never in the package ZIP, and
  package export remains data-free.

## Rollout sequence (per stage)

```text
legacy primary -> Forge shadow -> Forge primary with legacy fallback -> Forge primary only -> legacy retired
```

Legacy model paths are only retired after the consumer registry shows consumer-zero and the
benchmark/shadow/rollback gates pass (see `docs/generated/forge_model_consumer_registry.json`).
