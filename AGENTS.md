# Apply the Atlas Project Digital Twin design package

This package contains:

```text
AGENTS.md
docs/atlas_project_digital_twin_goal.md
docs/atlas_project_digital_twin_architecture.md
docs/atlas_project_digital_twin_contracts.md
docs/atlas_project_digital_twin_implementation_plan.md
docs/atlas_project_digital_twin_current_status.md
docs/atlas_project_digital_twin_agent_entrypoint.md
```

## PowerShell

From the KasaneCore repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\install_project_digital_twin_docs.ps1
```

Pass the extracted package directory when it is elsewhere:

```powershell
powershell -ExecutionPolicy Bypass -File C:\path\to\package\install_project_digital_twin_docs.ps1 `
  -RepoRoot C:\Users\kkens\code\KasaneCore
```

The installer creates a timestamped backup of the existing `AGENTS.md`.

## Bash

```bash
bash ./install_project_digital_twin_docs.sh /path/to/KasaneCore
```

## Start Codex or Claude

After applying:

```text
Read AGENTS.md and implement the active Atlas Project Digital Twin goal.
Start at PDT-0, follow current status, implement one work package at a time,
run the required tests, update current status, and continue sequentially.
Do not push, merge or weaken safety boundaries without explicit instruction.
```
