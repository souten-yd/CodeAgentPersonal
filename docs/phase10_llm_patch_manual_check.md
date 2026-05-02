# Phase 10 LLM Patch Manual Check Template

- 実行日:
- LLM endpoint:
- model:
- test target file:
- patch_generation_mode:
- run_id:
- patch_id:
- patch_type:
- generator:
- apply_allowed:
- quality_score:
- can_apply_reason:
- safety_warnings:
- quality_warnings:
- verification_status:
- reproposal generated? (yes/no):
- observed issue:
- notes:

## Example Result

- 実行日: 2026-05-02
- LLM endpoint: http://127.0.0.1:8080/v1
- model: local-model
- patch_generation_mode: llm_replace_block
- patch_type: replace_block
- generator: llm_replace_block
- apply_allowed: true
- quality_score: 0.82
- verification_status: passed
- reproposal generated?: no
- observed issue: none
