# AGENTS.md — KasaneCore 実装エージェント向け入口

このファイルは Codex / Claude などの実装エージェントが最初に読む入口です。

## Active P0 goal

| タスク | 正典入口 | 状態 |
|---|---|---|
| Atlas Play / Capsule / Portal | `docs/atlas_play_portal_capsule_goal.md` | Active / PR-PPC-0 |

## Read order

1. `docs/atlas_play_portal_capsule_goal.md`
2. `docs/atlas_play_spec.md`
3. `docs/atlas_capsule_portal_spec.md`
4. `docs/atlas_play_portal_capsule_current_status.md`
5. `docs/atlas_play_portal_capsule_implementation_plan.md`
6. `docs/atlas_play_portal_capsule_codex_entrypoint.md`
7. `docs/atlas_play_portal_capsule_review_corrections.md`

以前のAtlasコード生成完全性ゴールは完了済みです。この開発では上記文書と現在のコード・テストをsource of truthとします。

## Fixed decisions

- `/play`はAtlas専用とし、Lumenへ追加しない。
- Atlas headerはCapsule、Play、Plan Historyの順で右寄せする。
- PortalはLumen、Atlas、Echo、Nexusと同列の画面とする。
- Portal RunはAtlas Playの公開runtime contractを使う。
- Package、永続data、session data、一時dataを分離する。
- Portal dataは保存、snapshot、廃棄を選択可能にする。
- Package ExportにPortal dataを含めない。

## Implementation rules

- PR-PPC-0からPR-PPC-12まで順番に、一度に一つだけ実装する。
- 公開interfaceとversioned schemaを先に固定する。
- 対象ファイル、直接依存、直接呼び出し元、関連testだけ読む。
- 既存service、helper、schema、test fixtureを優先して再利用する。
- focused tests、syntax checks、affected testsの順に検証する。
- 計画だけで停止せず、実装、test、current status更新まで進める。
- workflow state、PlanPool、approval、critical event、allowed path、rollback、retry limitを弱めない。
- 実行していないtestを成功扱いしない。
- 各PRは小さく独立してreview可能にする。
