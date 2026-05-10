# Root Directory Inventory (PR4.66)

PR4.66 performs the first deliberately small root cleanup move after the PR4.65
inventory. It moves only low-risk utility files that are not root-keep files and
that are not directly executed by Docker, GitHub Actions, Runpod startup,
application import paths, or Audio/Echo/ASR/TTS/SBV2 runtime code.

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
  utilities, Windows-only helper utilities, and non-routine operator utilities.
- `docs/runbooks/`: Runpod checks, recovery procedures, CUDA/llama/ASR/TTS known
  good notes, snapshot procedures, and baseline procedures.
- `docs/refactor/`: split plans, route ownership notes, `main.py` split plans,
  and root cleanup plans.
- `tests/`: `test_*.py`, contract tests, and smoke tests.

## PR4.66 moved files

| Move | Destination | Move reason | Reference updates |
| --- | --- | --- | --- |
| `agent_runtime.py` -> `tools/agent_runtime.py` | `tools/` | Root Python helper with no direct checked runtime, Docker, Actions, README, or app reference; treated as a manual/operator utility. | No production references existed; inventory docs and generated JSON record the move. |
| `DLllama.bat` -> `tools/DLllama.bat` | `tools/` | Windows llama.cpp download helper had only docs/test mentions and no direct Docker, Actions, app import, Runpod entrypoint, or root startup dependency. | Updated CUDA regression doc/test references from root `DLllama.bat` to `tools/DLllama.bat`. |

PR4.66 intentionally does not move any file whose direct references include
Dockerfile COPY/install behavior, GitHub Actions execution paths, Runpod startup,
`main.py` runtime imports, or app runtime code.

## Current root-level file inventory

| File | Classification | Root decision | Move destination candidate | References fixed before move | Move caution |
| --- | --- | --- | --- | --- | --- |
| `.dockerignore` | root-keep | Keep in root as Docker build context metadata. | n/a | Docker/test contracts mention root `.dockerignore`. | Do not move; Docker build context would change. |
| `.gitignore` | root-keep | Keep in root as repository metadata. | n/a | Repository/tooling conventions. | Do not move. |
| `Dockerfile` | root-keep | Keep in root; Docker and CI build entrypoint. | n/a | `.github/workflows/docker-publish.yml`, `.github/workflows/runpod-test.yml`, Docker tests, runtime docs | Do not move; Docker build and CI path assumptions depend on it. |
| `README.md` | root-keep | Keep in root as repository landing page. | n/a | Runpod workflow and many project-context tests | Do not move; external and internal links assume root README. |
| `benchmark_mem.py` | tools-candidate | Candidate for later move, but high reference sensitivity. | `tools/` | `main.py`, `.github/workflows/runpod-test.yml`, `tests/test_phase30_3_llama_kv_cache_q8_contract.py`, docs | Update Runpod workflow/test references before moving. |
| `main.py` | root-keep | Keep in root; application entrypoint and current owner of high-risk runtime routes. | n/a | README, Runpod workflow, `scripts/export_route_inventory.py`, app routers/providers, many contracts | Do not move. Audio/Echo/ASR/TTS/SBV2 route ownership must remain unchanged. |
| `requirements-tts.txt` | root-keep | Keep in root as Docker dependency manifest. | n/a | `Dockerfile`, Docker dependency tests | Do not move unless Docker COPY/install order and tests are updated together. |
| `requirements.txt` | root-keep | Keep in root as primary dependency manifest. | n/a | `Dockerfile`, `README.md`, `main.py`, Runpod/start scripts, Docker tests | Do not move unless Docker, README, launchers, and tests are updated together. |
| `setup_style_bert_vits2_windows.bat` | high-risk-launcher | Keep in root for now; possible later tool move. | `tools/` plus runbook link | `main.py`, `scripts/start_codeagent.py`, SBV2 runtime, CUDA docs/tests | High-risk Windows/SBV2 launcher; update references and user docs first. |
| `setup_whisper_cpp_vulkan_windows.bat` | high-risk-launcher | Keep in root for now; possible later tool move. | `tools/` plus runbook link | `app/asr/service.py`, ASR Windows docs/tests, CUDA docs/tests | High-risk Windows ASR setup launcher; update references and user docs first. |
| `start.bat` | high-risk-launcher | Keep in root for now; possible later launcher/tool move. | `tools/` or documented launcher area | `README.md`, `main.py`, `scripts/start_codeagent.py`, `scripts/start_searxng_windows.py`, `app/nexus/router.py` | High-risk user-facing startup path; do not move before launcher compatibility plan. |
| `ui.html` | root-keep | Keep in root because current app/static tooling serves and checks it in place. | n/a until UI asset plan exists | `README.md`, UI scripts, Playwright/UI contracts, app startup helpers | Do not move in root cleanup PRs unless static serving and UI contracts are updated together. |

## Reference-source check policy

Before moving any root-level file in this or later cleanup PRs, check direct
filename references in these locations:

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
records current root files plus PR4.66 moved files in
`docs/generated/root_directory_inventory.json` for comparison.

## Low-risk moves completed in PR4.66

1. `agent_runtime.py` -> `tools/agent_runtime.py`
2. `DLllama.bat` -> `tools/DLllama.bat`

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

- PR4.66 does not touch WebSocket `/echo/stream`.
- PR4.66 does not change Audio/Echo runtime route ownership.
- PR4.66 does not change ASR/TTS/SBV2 execution code.
- PR4.66 does not change Dockerfile COPY instructions.
- PR4.66 does not change GitHub Actions execution paths.
- PR4.66 does not change Runpod startup or launcher scripts.
- PR4.66 does not add `sys.path` manipulation or alter app import paths.
