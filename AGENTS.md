# AGENTS.md — KasaneCore 実装エージェント向け入口

このファイルは Codex / Claude などの実装エージェントが最初に読む入口です。

## Active P0 goal

| タスク | 唯一の正典入口 | 状態 |
|---|---|---|
| Atlasコード生成完全性の根本改修 | [`docs/atlas_codegen_completeness_goal.md`](docs/atlas_codegen_completeness_goal.md) | Active / WP-0 |

このゴールでは、過去のAtlas品質計画、旧ロードマップ、旧Codex指示書を参照しないでください。現在のコードとテスト、および次の3文書だけをsource of truthとします。

1. `docs/atlas_codegen_completeness_goal.md`
2. `docs/atlas_codegen_completeness_current_status.md`
3. `docs/atlas_codegen_completeness_implementation_plan.md`

Codex goal modeではgoal文書のread order、work package順序、トークン削減規則に従い、各work packageの完了後にcurrent statusを更新してください。

## Implementation rules

- 一度に一つのwork packageだけ実装する。
- 対象ファイル、直接依存、直接呼び出し元、関連テストだけ読む。
- 既存service/helper/schema/test fixtureを優先して再利用する。
- focused tests、syntax checks、affected suiteの順に検証する。
- 計画整理だけで停止しない。
- PR作成・マージはユーザーの明示指示があるまで行わない。
- backend workflow_state / PlanPool authority、承認、critical-event判断、allowed paths、rollback、retry limitを弱めない。
- direct merge、remote push、self-apply、stable runtime mutation、Vue authority、arbitrary unbounded command executionを有効化しない。
- verification resultを捏造しない。
