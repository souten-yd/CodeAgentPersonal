# Atlas Runtime Progress and Resume/Rehydrate Hardening Agent Entrypoint

## Start Here

Read in this order:

1. `AGENTS.md`
2. `docs/atlas_runtime_progress_resume_hardening_current_status.md`
3. `docs/atlas_runtime_progress_resume_hardening_plan.md`
4. `docs/atlas_runtime_progress_resume_hardening_test_plan.md`
5. Target source files and tests

## First Package

Start with:

```text
AUIR-1: Fix LLM props initialization and token indicator safety
```

## User Bug Report

```text
Atlasでプラン生成後、承認して実行する。
その後開発を実行するが、LLMの生成状況がインジケータに表示されない。
インジケーターは停止している。

Log:
10:05:31 WARN [ctx] Could not fetch llm props: Cannot access '_current_n_ctx_ui' before initialization

別タブ移動やブラウザリロード後にAtlasへ戻ると、緑の枠だけ出てくる。
開発状況の表示やトークン生成のインジケータが一切表示されない。
```

## Initial Code Search

Search:

```text
_current_n_ctx_ui
Could not fetch llm props
llm props
tok-display
tok-total
tok-tps
atlas-claude-transcript
ContinuationResponse
on_progress
with_progress
_post_chat_stream
```

## Implementation Instructions

1. Fix the TDZ/initialization-order bug first.
2. Ensure props fetch failure is non-fatal.
3. Ensure token indicator is driven by Atlas runtime progress, not only chat metrics.
4. Add server-authoritative snapshot/replay for active run status.
5. Rehydrate Atlas UI on mode switch, tab return, and browser reload.
6. Make stale/reconnecting/stalled/terminal states visible.
7. Add regression tests.

## Do Not

- Do not hide the issue by suppressing all warnings.
- Do not rely on localStorage as the source of truth.
- Do not mark mock progress as real model evidence.
- Do not bypass Proposal / Safe Apply / Verification.
- Do not introduce external calls by default.
- Do not persist secrets.

## Done When

- `_current_n_ctx_ui` warning cannot reproduce.
- Active Atlas development shows LLM progress.
- Reload/tab switch restores development state.
- Empty green-frame-only state cannot reproduce.
- Tests and status docs are updated.
