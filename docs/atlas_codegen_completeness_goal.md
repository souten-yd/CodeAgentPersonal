# Atlas Code Generation Completeness Goal

> Status: Active P0 canonical goal  
> Codex goal-mode entrypoint  
> Baseline: current `main` after PR #1599  
> This goal is self-contained. Do not read older Atlas quality plans, old roadmaps, or prior Codex instruction documents.

## 1. Final goal

Atlas のコード自動生成を、ファイルやクラスの骨格を作る段階から、次の状態へ移行する。

- ユーザー要求を原子的な requirement として保持する。
- planner が各 requirement を具体的な PlanItem、対象ファイル、実装責務、受け入れ条件、検証方法へ割り当てる。
- planner から code generator、safe apply、verification、final rollup まで情報を失わない。
- コード生成は、最新のワークスペース、全体ゴール、完了済み実装、未完了 requirement を参照する。
- 各 PlanItem を `generate -> review -> apply -> verify -> context refresh` の順に一つずつ完了する。
- TODO、placeholder、空関数、固定値だけの仮実装、未接続module、不完全ファイルを成功扱いしない。
- 必須 requirement が missing / partial / planned / unverified の状態では `completed` を返さない。
- generation、review、apply、verification の失敗を、警告付き成功や skeleton fallback に変換しない。
- 失敗時は bounded regeneration、PlanItem分割、replan、または truthful stop に進む。
- 安全境界を緩和せず、実用的な大規模コード生成へ拡張できる構造にする。

最終成果は「コードが存在すること」ではない。  
**要求された挙動が実装され、既存機能へ接続され、観測可能な方法で検証されていること**である。

## 2. Codex read order

Codex のゴール機能では、必ず次だけを最初に読む。

1. `AGENTS.md`
2. `docs/atlas_codegen_completeness_goal.md`
3. `docs/atlas_codegen_completeness_current_status.md`
4. `docs/atlas_codegen_completeness_implementation_plan.md`
5. current status が示す現在の work package の対象ファイル
6. その直接依存、直接呼び出し元、関連テスト

禁止:

- 過去のAtlas品質計画、旧ロードマップ、旧Codex指示書を読むこと
- 毎work packageでリポジトリ全体を再走査すること
- 長い計画を最終報告へ再掲すること
- current status を無視して最初から調査し直すこと

現在のコードとテストが実装事実の source of truth である。行番号ではなくシンボル名で確認する。

## 3. Codex goal-run behavior

Codex は計画作成だけで停止せず、implementation plan の work package を順番に実装する。

各 work package で:

1. current status を確認する。
2. 指定された対象ファイルと関連テストだけ読む。
3. 既存helper/schema/service/test fixtureを再利用する。
4. 最小で一貫した変更を実装する。
5. focused tests と syntax checks を実行する。
6. failure が今回変更に起因する場合は修正する。
7. `docs/atlas_codegen_completeness_current_status.md` を更新する。
8. そのwork packageの受け入れ条件が満たされたら次へ進む。

次の条件では停止して、truthful blocker を記録する。

- critical / safety-sensitive decision が必要
- 破壊的変更の明示判断が必要
- allowed path、profile、envelope、retry limitを越える
- 実行環境がなく検証不能で、代替の信頼できる検証もない
- current mainと計画の前提が大きく異なり、局所修正では安全に進められない

単なる実装量の多さ、テスト時間、コンテキスト量を理由に確認を求めて停止しない。

## 4. Root causes to eliminate

### RC-1: generate-all-then-apply

複数PlanItemのproposalを同じ初期snapshotから先に生成し、後でまとめて適用すると、同一ファイルを触る後続itemが前段実装を保持できない。

必須変更:

```text
select item
-> read latest target
-> generate
-> review
-> apply
-> verify
-> refresh
-> select next item
```

全proposalの先行一括生成は禁止する。

### RC-2: planner contract loss

次の情報をplannerからPlanPool、PlanItem、proposal input、verificationまで保持する。

- original user request
- root goal
- selected architecture
- functional requirements
- non-functional requirements
- constraints
- requirement IDs
- item goal
- acceptance criteria
- expected changes
- verification contract
- rollback contract
- preserve behaviors
- dependencies

### RC-3: local-only generation context

code generatorが局所PlanItemだけを見る構造を廃止する。生成入力には最低限、次を含める。

```json
{
  "root_goal": "",
  "original_user_request": "",
  "selected_architecture": "",
  "global_constraints": [],
  "all_requirements": [],
  "requirements_for_this_item": [],
  "already_satisfied_requirements": [],
  "remaining_requirements": [],
  "completed_item_summaries": [],
  "current_item": {
    "goal": "",
    "description": "",
    "acceptance_criteria": [],
    "verification_contract": {},
    "target_files": []
  },
  "current_target_contents": {},
  "base_file_revisions": {},
  "project_symbols": [],
  "related_tests": [],
  "preserve_behaviors": []
}
```

### RC-4: unresolved self-review remains applicable

最終生成試行でもself-reviewが失敗したproposalは適用不可にする。

最低契約:

```json
{
  "status": "failed",
  "patch_content_available": false,
  "generation_failed": true,
  "apply_allowed": false,
  "unresolved_findings": []
}
```

warningを付けて返すだけで、safe apply可能な状態にしてはならない。

### RC-5: permissive completion semantics

変更ファイルがあることやitemが一件completedであることを、最終成功の根拠にしない。

`completed` の必須条件:

- 全必須requirementがPlanItemへ割り当て済み
- 全実装PlanItemに実変更evidenceがある
- 全必須requirementにimplementation evidenceがある
- 全必須requirementがtask-aware verificationを通過している
- missing / partial / planned / unverifiedが0件
- unresolved self-review findingが0件
- placeholder / stub / empty-body findingが0件
- integration findingが0件
- verification evidenceが実測である

### RC-6: skeleton fallbacks

次を実装成功経路から除去する。

- planner skeleton fallback
- requirement fallbackを実装可能な要件として扱う経路
- legacy `ImplementationExecutor._create_stub()`
- LLM failure時のappend fallback
- unknown action typeをcreateへ変換する挙動
- review例外時のapproved/proceed
- content上限超過時の文字列切り捨て

fallbackはreplan、failure、blocked、manual reviewのいずれかにする。コード骨格を捏造しない。

### RC-7: weak semantic schemas

弱いローカルモデル向けにschemaを浅く保つ場合でも、task-aware semantic validationを後段で必須にする。

生成結果は最低限、次のevidenceを持つ。

```json
{
  "file_changes": [],
  "satisfied_requirement_ids": [],
  "preserved_requirement_ids": [],
  "implemented_symbols": [],
  "behavioral_cases": [],
  "verification_cases": [],
  "known_limitations": [],
  "remaining_todos": []
}
```

`remaining_todos`、未解決limitation、未対応requirementがあれば成功proposalにしない。

### RC-8: insufficient stub detection

比率だけで判定しない。重要な一つの空関数でも失敗できる構造検査を追加する。

対象例:

- Python: `pass`、`NotImplementedError`、空body、固定値だけの主要処理
- JS/TS: 空event handler、空update/render、仮return、接続されていないexport
- HTML: 空container、未接続script/style、placeholder element
- CSS: 使用されていない必須class/animation
- game: input/update/render/collision/state/game-over/restartの欠落
- API: routeだけでservice処理がない
- UI: controlだけでevent接続がない

### RC-9: verification gaps

verificationが存在しない、skipped、環境不足の場合にcompletedへ変換しない。

task-aware verificationの例:

- Python syntax/import/unit test
- JS syntax/module import/browser console
- API request/response contract
- HTML/DOM interaction
- Playwright runtime smoke
- visual behavior contract
- requirement-specific static/runtime signal
- integration graph
- persistence/reload behavior

## 5. Revision precondition

proposalは生成時のbase revisionを記録する。

- single file: SHA-256または同等のcontent revision
- multi-file: pathごとのrevision map
- new file: absent marker

apply時にrevisionが一致しない場合:

1. applyしない
2. latest contentを再読込
3. proposalを再生成
4. 再self-review
5. 規定回数を超えたらneeds_revision

## 6. Failure handling

### Generation failure

空出力、invalid JSON、content missing、content too large、revision mismatchはfailure。

- placeholderを作るfallbackは禁止
- failure reasonを次試行へ渡す
- bounded retry後も失敗する場合はitem分割またはreplan
- 解決不能ならtruthful stop

### Verification failure

- 実装failureとtest failureを区別する
- implementationを直すべき場合にtestだけを変更しない
- bounded repairのallowed paths、risk、retry、command allowlistを維持する

### Verification unavailable

- completedにしない
- `applied_unverified` または `blocked`
- missing harness、command、evidenceを明示する

## 7. Safety invariants

すべてのwork packageで維持する。

- backend `workflow_state` / PlanPool authoritative
- UI is supervision/display only
- direct merge disabled
- remote git push disabled
- self-apply disabled
- stable runtime mutation disabled
- Vue authority/default disabled
- arbitrary unbounded command execution disabled
- raw source serving disabled
- fabricated verification results prohibited
- critical events require user judgment
- no execution during clarification
- no execution before post-clarification revision and gate evidence
- preserve profile, envelope, allowed-path, gate, rollback and retry boundaries
- destructive change is never auto-approved

## 8. Token-efficient execution rules

この節を唯一のトークン削減規則とする。

- 初回baselineだけ、本書、plan、current status、主要フローを読む。
- work package開始時はcurrent statusのNext work packageだけを入口にする。
- 対象ファイル、直接依存、直接呼び出し元、関連test以外を読まない。
- broad repository scanは対象symbolを特定できない場合だけ。
- 既存実装を再利用し、新しい抽象化は重複が明確な場合だけ追加する。
- Auto Reviewは通常実装中OFF。
- Full reviewはmilestone、execution/safety gate、最終統合、merge candidateだけ。
- testはfocused -> syntax -> affected suiteの順。
- 毎回master planを再要約しない。
- PR bodyや最終報告へ本書を複製しない。
- 最終報告はchanged files、tests、syntax checks、safety invariants、remaining blockers、next work packageだけ。
- トークン削減を理由に品質、verification、安全境界を弱めない。

## 9. Global acceptance scenarios

### A. Same-file sequential implementation

3件以上のPlanItemが同じHTML/JS/Pythonファイルを変更し、後続itemが前段実装を保持する。

### B. Browser game completeness

小規模ブラウザゲームで次を実装・検証する。

- player input
- enemy generation and movement
- primary interaction or shooting
- collision
- score/progress
- life/failure state
- game over
- restart
- entrypoint wiring
- no browser console error

### C. Existing repository feature change

既存helper/public contractを再利用し、無関係コードを上書きせず小規模機能追加を行う。

### D. Self-review rejection

規定回数の生成がstub/empty/incompleteの場合、applyせずgeneration failureまたはneeds_revisionになる。

### E. Requirement-complete rollup

必須requirementを一件未実装にするとcompletedにならない。

### F. Verification unavailable

test harnessを利用不能にすると、successを捏造せずapplied_unverifiedまたはblockedになる。

### G. Legacy path protection

legacy executor/fallbackからTODO stubが生成・成功扱いされない。

## 10. Definition of done

- implementation planの全必須work packageが完了
- same-file stale proposal overwriteが防止済み
- planner-to-generator contract lossがない
- unresolved self-review failureがapplyされない
- skeleton fallbackがsuccessに流れない
- partial/missing/unverified requirementがcompletedにならない
- task-aware verification evidenceが保存される
- global acceptance scenariosが自動テストで通る
- safety invariantsが維持される
- current statusがCompletedを示す
