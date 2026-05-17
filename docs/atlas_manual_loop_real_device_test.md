# Atlas Manual Loop Real Device Test

## 1. 目的
実機テスト前に、manual loopの最終smoke/checklistとreload recoveryを確認する。

## 2. 前提
- FastAPIを起動していること。
- UI3 / Atlas dashboardを開けること。
- llama-server接続は任意。
- safe_apply executorが未接続の場合、safe_apply実行がblockedでもよい。

## 3. 手順
1. PlanPoolを作成する。
2. DebugReview analyzed相当のitemを用意する（または既存UIでfailed→DebugReviewまで進める）。
3. Patch Proposalを生成する。
4. Patch Proposalを承認する。
5. PlanItem Draftを作成する。
6. PlanItemを承認する。
7. Manual safe apply candidatesに表示されることを確認する。
8. ページをreloadする。
9. pool/run/candidates/approval/continuationが復元されることを確認する。

## 4. 合格条件
- safe_apply candidateが表示される。
- reload後も状態が復元される。
- 自動safe_apply / verification / DebugReviewが走らない。

## 5. 既知の未実装
- safe_apply前backup（Change Snapshot backup）は未実装。
- rollbackは未実装。
- Nexus Context Refreshは未実装。
- Auto policyは未実装。
- Task/Agent APIは追加しない。

## 6. 次PR
- PR-ATLAS-PIPE-35: Change Snapshot backup before safe_apply。

- PR-ATLAS-PIPE-35以降、manual safe_apply前にChange Snapshot backupを保存する。
- PR-ATLAS-PIPE-35ではrollback/restoreはまだ手動実装なし。
- safe_apply実行時はsnapshot manifest pathを確認する。


## PR-ATLAS-PIPE-35B updates
- dry-runだけではPatch Proposalは出ない。
- Patch Proposalは failed verification → manual DebugReview analyzed 後に出る。
- 1/N completedでcompleted表示された問題はPR-35Bで修正。
- queued/dependency waitingが残っている場合はcompletedではなくpaused/waiting。
- PR-35でsafe_apply前snapshot backup済み。rollback/restoreはPR-36以降。


- Current PR: PR-ATLAS-PIPE-36C
- Next PR: PR-ATLAS-PIPE-37

- PR-36C unifies safe_apply executor, snapshot, and restore workspace root.


## PR-ATLAS-PIPE-36D updates
- manual safe_applyで実ファイルが変更されることを確認する。
- actual_file_changed / changed_files / workspace_root を確認する。
- restoreでupdate変更を元に戻せることを確認する。
- create変更は`confirm_delete_missing_before=false`では削除せずskipする。
- `confirm_delete_missing_before=true`で作成ファイルを削除できる。
- auto rollbackはまだない。
- restoreは手動操作のみ。


## PR-ATLAS-PIPE-36E updates
- Patch Proposal由来のPlanItem Draftでsafe_applyする場合、draft metadataに executor-readable patch/proposed_content があることを確認する。
- safe_apply後に actual_file_changed / changed_files / workspace_root を確認する。
- restoreで元に戻せることを確認する。
- content_missing の場合はPatch Proposalの実変更内容が不足している。

- PR-ATLAS-PIPE-36F updates
- Patch Proposal由来draft safe_applyのE2E assertionを厳密化した。
- safe_apply前後で実ファイル内容が old → new へ変わることを検証する。
- restoreが restored で、manual restoreにより new → old へ戻ることを検証する。
- content_missing は applied として通過できないことを検証する。

- Current PR: PR-ATLAS-PIPE-36F
- Next PR: PR-ATLAS-PIPE-37


- PR-39B: auto verification pass/fail E2Eを固定。project_pathなしではauto verificationしない。verification失敗時は停止のみ（auto restore/rollbackなし）。次はmanual restore suggestion。
