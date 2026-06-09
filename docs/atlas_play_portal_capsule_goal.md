# Atlas Play / Capsule / Portal Goal

> Status: Active
> Current package: PR-PPC-0

## Objective

KasaneCoreに、モバイルブラウザだけでAtlasプロジェクトの実行、確認、成果物化、保管、共有、再実行まで行える機能を追加する。

- **Play**: Atlas専用の`/play`コマンドとPlayボタンから、選択中プロジェクトを安全に実行する。
- **Capsule**: Playで動作確認済みのプロジェクトを、複数の起動対象を持てる配布用ZIPへ変換する。
- **Portal**: Lumen、Atlas、Echo、Nexusと同列の画面として、PackageのImport、Export、Run、Data管理、Snapshot、Fork to Atlasを提供する。

正式名称はPlay、Capsule、Portalとする。

## Read order

1. `AGENTS.md`
2. `docs/atlas_play_portal_capsule_goal.md`
3. `docs/atlas_play_spec.md`
4. `docs/atlas_capsule_portal_spec.md`
5. `docs/atlas_play_portal_capsule_current_status.md`
6. `docs/atlas_play_portal_capsule_implementation_plan.md`
7. `docs/atlas_play_portal_capsule_codex_entrypoint.md`

上記文書と現在のコード・テストをsource of truthとする。

## Fixed decisions

- `/play`はAtlas入力だけで解釈し、Lumenには追加しない。
- Atlas headerは右側に`Capsule`、`Play`、`Plan History`の順で表示する。
- 選択ファイルはentrypointだが、実行単位は選択中Atlas projectの`work` rootとする。
- 許可範囲内のHTML、JavaScript、CSS、asset、Python import、template、設定ファイルを関連ファイルとして扱う。
- Portal RunはAtlas Playの公開runtime contractを利用し、別のprocess runnerを作らない。
- Capsuleは複数launch profileとcomposite profileを持てる。
- Portal package ZIPは不変とし、実行時だけ隔離領域へ展開する。
- Package、永続data、session data、cache/tempを分離する。
- Portalで生成したdataはSave、Snapshot、Discardを選択できる。
- Package ExportにPortalの保存dataを含めない。

## Safety requirements

- 既存のworkflow state、PlanPool、approval、critical event、allowed path、rollback、retry limitを弱めない。
- 任意の無制限command endpointを追加しない。
- host filesystemやtemporary service portを直接公開しない。
- import packageはquarantine検証前に登録・実行しない。
- Portal package本体を書き換えない。
- Play success、verification、test resultを未実行のまま成功扱いしない。
- Stop、failure、expiry、server recovery後にprocess tree、port、runtime directoryを残さない。

## Completion conditions

1. Atlas専用PlayがHTML、Python、ASGI、Node/Viteを実行できる。
2. 関連ファイルをproject root内で読み込み、許可されたものだけ編集・保存できる。
3. Preview、Logs、Restart、Stop、cleanupがモバイルから操作できる。
4. path traversal、absolute path、drive/UNC、link escapeがfail closedになる。
5. Play成功証拠から複数profile Capsuleを生成しPortalへ登録できる。
6. PortalでImport、Export、Run、Data、Snapshots、Fork to Atlasが利用できる。
7. Portal dataを保存、snapshot、廃棄、recoveryできる。
8. Package Exportへ保存dataを混入させない。
9. security、process cleanup、API、UI、iPhone相当viewportのE2E testが通る。
10. PR-PPC-0からPR-PPC-12までのstatusに実行済みtest evidenceが記録される。
