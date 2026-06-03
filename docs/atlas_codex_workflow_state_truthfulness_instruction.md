# Codex 指示書 — read-only workflow_state コントラクトの真実性修正（プロファイル/証拠連動）

> このファイルは Codex のゴール機能にそのまま渡せる単一ゴールの実装指示。
> 先に `docs/atlas_full_automation_codex_entrypoint.md` と
> `docs/atlas_corrective_pr_split_plan_after_1510.md` の
> 「Global token-saving operating rules for Codex」「Global hard constraints」を読み、
> 本PRセクションで列挙したファイルのみを読むこと（広域スキャン禁止）。

---

## 背景（なぜこの修正が必要か）

read-only の `atlas.workflow_state.v1` コントラクト（Atlas Next 監視シェル用の表示専用面）が
**恒久的に古い状態を報告**しており、監視者が「実行は不可能」と誤読する。実際には manifest
（`docs/atlas_automation_phase_manifest.json`）は `current_level: level_8_fully_autonomous_code_agent`,
`level1_execution_enabled: true`, `autonomous_execution_enabled: true`,
`practical_full_automation_complete: true` を報告しており、完全自動コード生成は
プロファイル連動の実行経路（`agent/atlas_automation_profile_resolver.py` +
`agent/atlas_guarded_operator_loop_service.py` + `app/atlas/automation_safety_profile.py`）で
**既に有効**である。

### 重要な事実確認（調査済み）

- `build_read_only_workflow_state`（`app/atlas/workflow_state_contract.py`）と
  `Level1GuardedExecutionSkeleton.build_disabled_level1_contract`
  （`app/atlas/level1_guarded_execution.py`）の消費者は **read-only 表示エンドポイント2つ
  （`app/api/atlas_workflow_state.py`, `app/api/atlas_pipeline.py:2024,2060`）とテストのみ**。
- これらは **完全自動コード生成の実行経路には一切含まれない**。よって「このコントラクトに
  17ゲート証拠を配線すれば実行が有効になる」という見解は誤り。配線しても実行挙動は変わらない。
- このコントラクトは **許容プロファイル1-3（review_only / guarded_single_action /
  supervised_bounded_auto）の監視・表示面として必要** なので削除しない。問題は
  「常に level_0 + SCALE-94 古い文言を返す」という **真実性の欠如** のみ。

## 判断

- **削除しない**（プロファイル1-3の監視面として必要、かつ full-auto の可観測性に必要）。
- **修正する**：表示専用は維持したまま、**アクティブなプロファイルと実証拠に連動**させ、
  古い `SCALE-94 ... not callable` / `not callable in SCALE-96` 文言を撲滅する。
- **新しい実行能力は一切追加しない**。本PRは「正しく報告する」だけのレポート真実性修正。

---

## 設計

### 不変条件（絶対に後退させない）

- 表示専用維持：`vue_execution_enabled:false`, `vue_source_of_truth:false`,
  `mutation_endpoints_enabled:false`, すべての `*_action_enabled:false`,
  `callable_execution_route_enabled:false`, `execution_performed:false`,
  `mutation_performed:false`。read-only エンドポイントの `primary_cta.enabled` は **false のまま**。
- `backend_workflow_state_authoritative:true`、UI 非権威を維持。
- 後方互換：既存キーは削除・改名しない。値の更新と新規キー追加のみ。
- safety-sensitive / critical 判定や禁止フラグの緩和は禁止。

### 修正方針

read-only コントラクトを **profile_resolution（`normalize_automation_profile` の出力）+ manifest +
呼び出し元が渡す artifacts** から導出する。表示する `preview_runtime_level` / ゲート証拠 /
チェックポイント文言を「実際のアクティブ状態」に一致させる。

---

## 実装タスク（順に実施）

### 1. ゲート証拠マップに実証拠を反映（`app/atlas/level1_guarded_execution.py`）

- 既存 `build_level1_gate_source_map()` は **ゼロ証拠デフォルトとして残す**（後方互換）。
- 新規 `build_level1_gate_source_map_with_evidence(*, artifacts, profile_resolution, manifest)` を追加。
  各 gate_id を実証拠源にマップする：
  - `snapshot_restore`←`artifacts["snapshot"]` / `patch_transaction`←`artifacts["transaction"]` /
    `risk_classification`←`artifacts["risk"]` / `dry_run_proof`←`artifacts["dry_run"]` /
    `allowlisted_verification`←`artifacts["allowlist"]` / `rollback_readiness`←`artifacts["rollback"]` /
    `artifact_capture`←`artifacts["artifact_capture"]` / `stop_kill_switch`←`artifacts["stop"]` /
    `loop_bounds`←`artifacts["loop_bound"]` または profile bounds の存在。
  - `explicit_approval_token`←metadata の承認トークン有無（無ければ `missing_evidence`）。
  - `self_improvement_gate`←`artifacts["self_improvement"]` または profile `self_improvement` フラグ。
  - 常時強制ポリシー系（`remote_git_restriction`, `data_root_path_safety`,
    `forbidden_command_execution_policy`, `backend_authority_enforcement`,
    `ui_non_authority_enforcement`, `audit_log`）は **policy_enforced** として
    `evidence_available:true`（ポリシーが常時存在するため）。
- `current_status` を `satisfied`（証拠あり）/`policy_enforced`（常時強制）/`missing_evidence`（未生成）
  のいずれかに設定。`blocker_reason` は真に欠落しているゲートのみ設定し、それ以外は空文字。
- `blocker_reason` / `execution_relevance` から **`SCALE-94` / `SCALE-96` / `not callable` の
  文字列リテラルを完全撤去**。チェックポイント文言は manifest の `current_automation_track` から導出。
- `build_disabled_level1_contract` を `build_level1_contract(*, artifacts=None,
  profile_resolution=None, manifest=None)` に一般化（旧名は disabled/ゼロ証拠デフォルトの薄い
  ラッパとして残す）。`enabled`/`runtime_level`/`level1_execution_enabled` を profile_resolution
  + manifest から導出。`missing_evidence_count`/`satisfied_gate_count` を証拠マップから再計算。
  `mutation_performed`/`execution_performed` は **false 固定**。

### 2. コントラクト組み立て（`app/atlas/workflow_state_contract.py`）

- `build_read_only_workflow_state(...)` に `profile_resolution: dict | None = None` を追加。
- `preview_runtime_level` を `profile_resolution["runtime_level"]`（無ければ manifest 既定）から導出。
  恒久 `level_0_manual_only` のハードコードを廃止。`level1_execution_enabled` は manifest/profile から。
- artifacts + profile_resolution + manifest を skeleton と `_build_guarded_execution_review` に渡す。
- `_build_guarded_execution_review`：`checkpoint` を manifest の現行トラックから導出。
  `blocked_reasons` は真に欠落のゲートのみ。`endpoint_contract_status` を
  `read_only_display_of_active_backend_state` に。
- `primary_cta`：`enabled:false` は維持しつつ、`reason` を真実に
  （例：「Read-only supervision view. 実行は backend guarded operator loop /
  認証付き実行経路で行われ、本エンドポイントは実行しない」）。
- 新規エコーフィールド `active_profile` / `active_envelope` / `autonomous_loop_active` を
  profile_resolution から追加（表示のみ）。既存キーは保持。

### 3. 呼び出し元の配線（`app/api/atlas_workflow_state.py`, `app/api/atlas_pipeline.py:2024`）

- `agent/atlas_automation_features.py::load_full_automation_state` で永続化された自動化状態を読み、
  `agent/atlas_automation_profile_resolver.py::normalize_automation_profile` で解決した
  `profile_resolution` を `build_read_only_workflow_state` に渡す。
- **フェイルクローズ**：読み込み失敗時は review_only 解決（level_0）に既定し、旧来の安全挙動を維持。

### 4. テスト

- 既存の「level_0/missing_evidence ハードコード」を検証しているコントラクトテストを
  プロファイル導出挙動に更新（review_only→level_0＋missing/policy、autonomous_dev_agent＋
  active envelope＋全 artifacts→上位 level＋satisfied）。
- 新規 `tests/test_atlas_workflow_state_truthfulness_contract.py`：
  - 全プロファイルで read-only 不変条件が成立（実行/変更なし、vue 非権威、全 action_enabled=false、
    `primary_cta.enabled=false`）。
  - 出力に `SCALE-94` / `SCALE-96` / `not callable` リテラルが**残らない**。
  - artifacts に応じてゲート証拠が変化（例：dry_run=true→`dry_run_proof` satisfied）。
  - `preview_runtime_level` がアクティブプロファイルを反映。

### 5. 構文・安全チェック

- 変更 Python は `python -m py_compile`。新規実行能力ゼロを grep で確認
  （`requires_human_approval` と禁止フラグ群が不変）。

---

## 制約

- 後方互換（新引数はデフォルト付き、旧関数名は維持）。既存キー削除・改名禁止。
- 安全ゲート緩和禁止。本PRは「正しく報告する」方向のみで、実行能力は増やさない。
- 巨大ファイル（`main.py` / `ui.html`）は触らない。
- UI 実装・非同期化は対象外。

## 受け入れ条件

- read-only エンドポイント出力が、アクティブプロファイル（review_only / guarded_single_action /
  supervised_bounded_auto / autonomous_dev_agent）に応じた `preview_runtime_level` とゲート証拠を返す。
- 出力に `SCALE-94` / `SCALE-96` / `not callable` が一切現れない。
- 全プロファイルで read-only 不変条件が維持される（実行/変更なし、CTA disabled）。
- `pytest -q tests/test_atlas_*workflow_state*.py tests/test_atlas_guarded_execution_review_*.py
  tests/test_atlas_workflow_state_truthfulness_contract.py` が緑。

## PR分割方針

本修正はソース3ファイル＋テストで完結するため **単一PR**（`PR-ATLAS-WS-TRUTHFULNESS`）を基本とする。
ただし呼び出し元配線（タスク3）が想定外の面（エンドポイント認証等）に波及する場合は分割する：

- **PR-A**：タスク1+2+4（純粋関数のプロファイル/証拠連動＋テスト、呼び出し元変更なし）。
- **PR-B**：タスク3（2エンドポイントの配線）＋統合テスト。

## 成果物

- 上記コード変更一式＋新規テスト。変更は指定の作業ブランチにコミット。
- コミットメッセージに目的を明記し、受け入れ条件のテスト結果を本文に記載。
- PR本文に本計画やdiffを長文転記しない（token-saving rules 準拠）。
</content>
</invoke>
