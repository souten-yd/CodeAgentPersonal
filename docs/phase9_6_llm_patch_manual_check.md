# Phase 9.6 LLM Patch Manual Check

## 1) LLM endpoint起動
```bash
llama-server --host 0.0.0.0 --port 8080 ...
```

## 2) 環境変数
```bash
export CODEAGENT_LLM_BASE_URL=http://127.0.0.1:8080/v1
export CODEAGENT_LLM_MODEL=local-model
```

## 3) アプリ起動
CodeAgentPersonal を通常手順で起動する。

## 4) Task実行
Plan生成 → Review → Approval で `execution_ready` まで進める。

## 5) Safe Apply Preview 実行
- `allow_update=true`
- `preview_only=true`
- `apply_patches=false`
- Patch Generation Mode = `LLM replace block preview`

## 6) 実行後確認
`/api/runs/{run_id}/patches` で以下を確認:
- `patch_type=replace_block`
- `generator=llm_replace_block`
- `llm_raw_output_preview`
- `can_apply_reason`
- `original_block` / `replacement_block`
- `unified_diff`
- `apply_allowed`

## 7) apply_allowed=true の場合のみ
- UIでdiff確認
- Approve Patch
- Apply Approved Patch
- `verification_status` と `verification_summary` を確認

## 8) 失敗時の確認先
- `ca_data/runs/<run_id>/patches/*.patch.json`
- `safety_warnings`
- `can_apply_reason`
- app logs
- LLM endpoint logs
