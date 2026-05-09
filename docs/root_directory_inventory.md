# Root Directory Inventory (PR4.65)

PR4.65 is an inventory-only cleanup preparation PR. It freezes the current
repository-root files, cleanup ownership, reference-check policy, and next-step
risk groups. It does **not** move any root-level file and does not change import
paths, Docker COPY rules, GitHub Actions paths, Runpod launchers, Audio/Echo
runtime code, or WebSocket `/echo/stream` ownership.

Machine-readable snapshot: `docs/generated/root_directory_inventory.json`.
Regenerate with:

```bash
python scripts/inventory_root_files.py
```

## Classification rules

### Keep in repository root

Keep a file in root when it is one of the following:

- `main.py`
- `Dockerfile`
- `docker-compose.yml`, `compose.yml`, or other compose entrypoints
- `pyproject.toml`
- `requirements*.txt`
- `README.md`
- `LICENSE`
- `.gitignore`
- `.dockerignore`
- Files directly referenced by GitHub Actions, Docker build, Runpod launchers,
  app startup, or the current runtime entrypoint

### Move candidates

- `scripts/`: `check_*.py`, `export_*.py`, `collect_*.py`, `diagnose_*.py`,
  `verify_*.py`, one-shot execution scripts, and CI helper scripts.
- `tools/`: manual repair tools, local validation tools, migration/repair/debug
  utilities, and non-routine operator utilities.
- `docs/runbooks/`: Runpod checks, recovery procedures, CUDA/llama/ASR/TTS known
  good notes, snapshot procedures, and baseline procedures.
- `docs/refactor/`: split plans, route ownership notes, `main.py` split plans,
  and root cleanup plans.
- `tests/`: `test_*.py`, contract tests, and smoke tests.

## Root-level file inventory

| File | Classification | Root decision | Move destination candidate | References fixed before move | Move caution |
| --- | --- | --- | --- | --- | --- |
| `.dockerignore` | root-keep | Keep in root as Docker build context metadata. | n/a | Docker/test contracts mention root `.dockerignore`. | Do not move; Docker build context would change. |
| `.gitignore` | root-keep | Keep in root as repository metadata. | n/a | Repository/tooling conventions. | Do not move. |
| `DLllama.bat` | tools-candidate | Candidate for later move; not moved in PR4.65. | `tools/` or `docs/runbooks/`-linked Windows tools area | `docs/cuda_regression_v2_7_diff.md`, `tests/test_cuda_regression_v2_7_diff_contract.py` | Update Windows/CUDA runbook and contract references first. |
| `Dockerfile` | root-keep | Keep in root; Docker and CI build entrypoint. | n/a | `.github/workflows/docker-publish.yml`, `.github/workflows/runpod-test.yml`, Docker tests, runtime docs | Do not move; Docker build and CI path assumptions depend on it. |
| `README.md` | root-keep | Keep in root as repository landing page. | n/a | Runpod workflow and many project-context tests | Do not move; external and internal links assume root README. |
| `agent_runtime.py` | needs-investigation | Do not move until manual usage is confirmed. | `tools/` if proven to be an operator utility | No direct checked runtime reference found by the inventory script. | Confirm whether users launch it directly from root. |
| `benchmark_mem.py` | tools-candidate | Candidate for later move, but high reference sensitivity. | `tools/` | `main.py`, `.github/workflows/runpod-test.yml`, `tests/test_phase30_3_llama_kv_cache_q8_contract.py`, docs | Update Runpod workflow/test references before moving. |
| `main.py` | root-keep | Keep in root; application entrypoint and current owner of high-risk runtime routes. | n/a | README, Runpod workflow, `scripts/export_route_inventory.py`, app routers/providers, many contracts | Do not move. Audio/Echo/ASR/TTS/SBV2 route ownership must remain unchanged. |
| `requirements-tts.txt` | root-keep | Keep in root as Docker dependency manifest. | n/a | `Dockerfile`, Docker dependency tests | Do not move unless Docker COPY/install order and tests are updated together. |
| `requirements.txt` | root-keep | Keep in root as primary dependency manifest. | n/a | `Dockerfile`, `README.md`, `main.py`, Runpod/start scripts, Docker tests | Do not move unless Docker, README, launchers, and tests are updated together. |
| `setup_style_bert_vits2_windows.bat` | high-risk-launcher | Keep in root for now; possible later tool move. | `tools/` plus runbook link | `main.py`, `scripts/start_codeagent.py`, SBV2 runtime, CUDA docs/tests | High-risk Windows/SBV2 launcher; update references and user docs first. |
| `setup_whisper_cpp_vulkan_windows.bat` | high-risk-launcher | Keep in root for now; possible later tool move. | `tools/` plus runbook link | `app/asr/service.py`, ASR Windows docs/tests, CUDA docs/tests | High-risk Windows ASR setup launcher; update references and user docs first. |
| `start.bat` | high-risk-launcher | Keep in root for now; possible later launcher/tool move. | `tools/` or documented launcher area | `README.md`, `main.py`, `scripts/start_codeagent.py`, `scripts/start_searxng_windows.py`, `app/nexus/router.py` | High-risk user-facing startup path; do not move before launcher compatibility plan. |
| `ui.html` | root-keep | Keep in root because current app/static tooling serves and checks it in place. | n/a until UI asset plan exists | `README.md`, UI scripts, Playwright/UI contracts, app startup helpers | Do not move in root cleanup PRs unless static serving and UI contracts are updated together. |

## Reference-source check policy

Before moving any root-level file in PR4.66 or later, check direct filename
references in these locations:

1. `Dockerfile`
2. `.github/workflows/*`
3. `scripts/*`
4. `app/*`
5. `main.py`
6. `README.md`
7. `docs/*`
8. `tests/*`

Confirm specifically that the filename is not directly executed by GitHub
Actions, copied/installed by Docker, called by a Runpod launcher, imported by app
runtime (app runtime), or asserted by a contract test. `scripts/inventory_root_files.py`
records these references in `docs/generated/root_directory_inventory.json` for
comparison, but PR4.65 does not rewrite any path.

## Low-risk group for PR4.66 candidates

Low-risk means “eligible for investigation first”, not “safe to move without
updating references”. Current candidates:

1. `agent_runtime.py` -> likely `tools/`, only after confirming no user-facing
   root launch contract exists.
2. `DLllama.bat` -> likely `tools/`, only after updating CUDA docs/tests.

## High-risk group: do not move yet

Do not move these until a dedicated compatibility plan updates every reference
and contract in the same PR:

- `main.py`
- `Dockerfile`
- `README.md`
- `.dockerignore`
- `.gitignore`
- `requirements.txt`
- `requirements-tts.txt`
- `ui.html`
- `benchmark_mem.py`
- `start.bat`
- `setup_style_bert_vits2_windows.bat`
- `setup_whisper_cpp_vulkan_windows.bat`

## Runtime and route-ownership guardrails

- PR4.65 does not touch WebSocket `/echo/stream`.
- PR4.65 does not change Audio/Echo runtime route ownership.
- PR4.65 does not change ASR/TTS/SBV2 execution code.
- PR4.65 does not change Dockerfile COPY instructions.
- PR4.65 does not change GitHub Actions execution paths.
- PR4.65 does not change Runpod startup or launcher scripts.
- PR4.65 does not add `sys.path` manipulation or alter app import paths.
