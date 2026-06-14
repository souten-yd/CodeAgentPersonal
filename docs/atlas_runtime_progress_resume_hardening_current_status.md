# Atlas Runtime Progress and Resume/Rehydrate Hardening Current Status

## Track

AUIR: Atlas UI Runtime Progress and Resume/Rehydrate Hardening

## Overall Status

```text
status: ready_to_start
current_package: AUIR-1
next_action: fix LLM props initialization and token indicator safety
```

## User-Observed Bug

```text
Atlasでプラン生成後、承認して実行する。
その後開発を実行するが、現状のLLMの生成状況がインジケータに表示されない。
インジケーターは停止している状況であった。

Log:
10:05:31 WARN [ctx] Could not fetch llm props: Cannot access '_current_n_ctx_ui' before initialization

別タブ移動やブラウザリロード後にAtlasへ戻ると、緑の枠だけ出てくる。
開発状況の表示やトークン生成のインジケータが一切表示されない。
```

## Current Hypothesis

1. `_current_n_ctx_ui` is read before initialization, probably due to JS TDZ with `let`/`const`.
2. LLM props fetch failure may abort or interrupt UI startup chain.
3. Approved Atlas execution/development LLM calls are not attached to the same progress indicator path as chat/plan.
4. Atlas shell state is ephemeral and not fully rehydrated from backend after reload.
5. Missed progress events are not replayed after reconnect.

## Active Package

### AUIR-1: Fix LLM props initialization and token indicator safety

### Required Code Investigation

Search and inspect:

```text
_current_n_ctx_ui
fetch llm props
llm props
tok-display
tok-total
tok-tps
atlas-claude-transcript
setMode('atlas')
mobSwitch('atlas')
DOMContentLoaded
window.onload
setInterval
ATLAS_LLM_STREAMING
with_progress
on_progress
ContinuationResponse
```

### Acceptance Checklist

- [ ] `_current_n_ctx_ui` is declared/initialized before any reads.
- [ ] LLM props fetch failure is caught and does not stop Atlas startup.
- [ ] Token indicator can render active run progress even if LLM props are unavailable.
- [ ] A test or browser smoke reproduces old TDZ failure and proves it fixed.
- [ ] Current status doc is updated with changed files and evidence.

## Evidence Log Template

Append one block per package completion:

```text
Completed package:
Status:
Changed modules/files:
Behavior implemented:
Focused tests:
Syntax checks:
Affected tests:
Real model evidence:
Atlas UI evidence:
Reload/resume evidence:
Unavailable checks:
Safety invariants:
Remaining gaps:
Next package:
Blocker:
```

## Package Queue

```text
AUIR-1: Fix LLM props initialization and token indicator safety
AUIR-2: Durable Atlas run progress event model
AUIR-3: Atlas tab reload/resume rehydration
AUIR-4: Live indicator reconnection and stale/stalled state UX
AUIR-5: Regression tests and mobile/browser reload smoke
AUIR-6: Return to PIBIH-1 LLM planning timeout hardening
```
