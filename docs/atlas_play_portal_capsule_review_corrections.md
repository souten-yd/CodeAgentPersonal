# Codex / Claude 指示書 — Atlas Play / Capsule / Portal 計画の補正反映

> このファイルは、現行コードをレビューした結果を Play / Capsule / Portal の正典へ
> 取り込むための補正指示です。すべて安全方向（より止める／境界を明確化する）のみ。
> source of truth は次のとおり:
> `AGENTS.md`, `docs/atlas_play_portal_capsule_goal.md`, `docs/atlas_play_spec.md`,
> `docs/atlas_capsule_portal_spec.md`, `docs/atlas_play_portal_capsule_current_status.md`,
> `docs/atlas_play_portal_capsule_implementation_plan.md`,
> `docs/atlas_play_portal_capsule_codex_entrypoint.md`, および本ファイル。

---

## このファイルの位置づけと取り込み手順

1. PR-PPC-0 に着手する前に、本ファイルの **C1–C5 / O1–O3 / S1** を
   `goal.md`（safety requirements・fixed decisions・既知の制限）、
   `implementation_plan.md`（PR分割・threat model・テスト）、
   `current_status.md`（baseline observations）へ反映する。
2. `AGENTS.md` の Read order 末尾に本ファイルを追加する。
3. 反映後に通常の execution loop（contracts → tests → 実装 → status更新）へ入る。

本ファイルは計画を上書きするものではなく、不正確な前提の訂正と、後で security で
巻き戻しになる箇所の前倒し確定が目的。

---

## C1 — baseline 記述の訂正と lifespan フックの配置（検証済み事実）

### 事実
- 本番 entrypoint は `main:app`。`main.py` L209 `app = FastAPI(lifespan=lifespan)`、
  L125–128 で `from app.server import (... include_routers ...)`、L210 `include_routers(app)`、
  L211 `app.include_router(nexus_router, ...)`。`main.py` は直接 route を約143本登録。
- `app/server.py` の `create_app()` / `include_routers()` は存在するが、`create_app()` は
  「main.py から application 構築を切り出す途中段階の skeleton」で本番未使用。
  本番に効くのは `main.py` が呼ぶ `include_routers(app)` の経路。

### 直し
- `current_status.md` の「Router registration is centralized in `app/server.py`」を
  次へ訂正:「新 router は `app/api/*` に追加し `app/server.py:include_routers()` へ登録する。
  ただし lifespan・middleware・直接 route は `main.py` 側にあり、本番 app は `main:app`」。
- **PR-PPC-4 / PR-PPC-11 の startup orphan reconciliation（process / port / staging root /
  未完了 commit の回収）は、`main.py` の lifespan に登録する。** `app/server.py` だけに
  置くと本番起動経路では回収が走らない。
- 回帰テスト: 起動時に reconciliation hook が必ず呼ばれることを検証（hook 未登録＝失敗）。

---

## C2 — 脅威モデルの「実行境界の新設」を明記（検証済み事実）

### 事実
- `app/atlas/` 配下に `subprocess` / `Popen` / `os.system` / `create_subprocess` は皆無。
  Atlas は現状一度も実プロセスを実行していない。
- `app/atlas/level1_disabled_command_runner.py` は `RUNTIME_LEVEL = "level_0_manual_only"` で
  恒久的に `runner_disabled_until_level1_transition`。command は
  `app/atlas/verification_allowlist.classify_verification_command` で分類されるのみで実行されない。

### 直し（PR-PPC-0 threat model に明記）
- Play / Portal の実行は **「ユーザーが起動する対象アーティファクトの runtime」** であり、
  **「エージェントによる command の自律実行」ではない**。これは Level 0–4 の自律実行
  safety model とは独立した新しい信頼境界である旨を threat model 冒頭に定義する。
- 新 Launch Adapter の許可判定は `verification_allowlist` とは **別物として新設**し、
  両者は互いに権限を貸さない（Launch Adapter が verification allowlist を緩めない／
  verification 経路が Launch Adapter を起動しない）ことを明記。
- 不変条件テスト: Play / Portal の起動経路から `level1_disabled_command_runner` や
  `workflow_state` authority、PlanPool approval が起動・変更されないこと。

---

## C3 — Reverse proxy の分割と必須ゲート化

### 直し（PR-PPC-5 を分割）
- **PR-PPC-5a**: session 紐付け static / session serving（`file://` も一時 port 直公開もしない）。
- **PR-PPC-5b**: loopback 所有 port への reverse proxy、WebSocket / SSE forwarding、
  path/base/location/cookie rewrite。

### blocking gate（緑必須。長いテストリストへ埋没させない）
- cross-session の port / session へのアクセス拒否
- proxy-target injection 拒否（任意ホストへ転送できない）
- origin / host 検証
- redirect / cookie / location rewrite 後に project / session 外へ越境しない
- open-proxy 挙動が存在しない

理由: 差別化機能の中で最も CVE 化しやすい面。単一 PR・単一リストに圧縮しない。

---

## C4 — composite（多サービス DAG）実行 slice の新設

### 事実
現計画は PR-PPC-3 で composite DAG を validation し、PR-PPC-9 のテストで初めて composite を
実起動する構成。単一プロセスより難度が高い（readiness gating、部分失敗時の全体 cleanup、
port 協調、起動順）にもかかわらず、composite **実行** の専用実装・テスト PR が無い。

### 直し
- PR-PPC-4 は単一プロセス（static web + Python script）で確定（現計画どおり）。
- **PR-PPC-4b** を新設し、composite の実起動を担う:
  readiness / health gating、依存起動順、部分失敗時の全 child cleanup、port 協調を実装・テスト。
- PR-PPC-9 の composite startup テストは PR-PPC-4b の通過を前提とする。

---

## C5 — Windows child-tree cleanup を一級要件に

### 背景
実運用は Windows（RX 9070 XT）。孤児プロセス（長命 child）リークの最大リスクは Windows 固有で、
Job Object 経由の child-tree kill が必須（Linux の process group / setsid とは別物）。
CI が Linux 中心だと、cleanup 保証が一番効いてほしい Windows でだけ未検証になる逆転が起きる。

### 直し（PR-PPC-4 / 11 / 12）
- Windows Job Object による child-tree kill と port release を、独立した必須テストにする。
  「platform-specific path behavior」へ埋めない。
- status evidence の要求: Job Object kill の unit / contract test、および Windows 手動 E2E
  チェックリスト項目（stop / failure / restart 後に child process・port・staging directory が残らない）。
- Linux でしか自動検証できない場合は、その制限を status に明記し、Windows 用の最強の
  contract test を残す（未実行を成功扱いしない）。

---

## O1 — Terminal タブの矛盾解消（過剰・曖昧制限）

PR-PPC-6 は「Terminal タブ」を出しつつ「no general host shell」を課しており名称と機能が衝突。
- read-only **Console**（session process の stdout / stderr 表示 + 限定 stdin）として再定義し、
  タブ名も `Console` にする。対話 host shell は作らない。
- 「session PTY contract」を採用する場合も、host shell ではなく session 単一プロセスに束縛された
  入出力であることを spec に明記。

---

## O2 — manifest の free-form command 禁止を「既知の制限」として明記

`portal-package.json` に free-form shell command を持たせない方針は妥当（過剰ではない）。
ただし Makefile target や独自 bootstrap を持つアプリは v1 では Capsule 化できない。
- `goal.md` に **既知の制限** として明記し、後から「バグ」として再発見されないようにする。
- 将来対応する場合も「構造化 adapter の拡張」で行い、free-form command 復活はしない。

---

## O3 — Data Backup を将来 bundle へ合成可能に設計

PR-PPC-10 の「Export = package のみ／runtime data を含めない」は v1 として正しい。
将来「seed data 付きデモを 1 個で共有」需要に備え、
- Data Backup を独立・version 化・署名可能な形式で設計し、後で
  `package + signed data snapshot` の bundle へ合成できる余地だけ確保する（今は別物のまま）。

---

## S1 — untrusted package 実行の隔離方針を確定（最重要・PR-PPC-0 で決定）

### 事実
計画の sandbox は path / process 境界どまりで OS レベル隔離が無い。にもかかわらず trust state に
`untrusted imported package` を置くと、アーキテクチャが提供できない安全保証を示唆してしまう。
import を local で実プロセス起動する責任は Portal が負う。

### 要決定（どちらかを PR-PPC-0 で固定し goal.md safety requirements に記載）
- **(a) OS 隔離を導入**: untrusted 実行を OS レベルで隔離する。
  Windows = restricted token / AppContainer / Job Object + network・FS 制限、
  Linux = user namespace + seccomp / bubblewrap 相当。
- **(b) 実行を既定で禁止**: untrusted は既定で Run 不可。明示 override 時のみ
  「隔離されておらず安全保証は無い」と警告して起動。trust state は強制でなく **助言** と文書化。

### 共通要件
- 「untrusted = 安全に実行できる」と誤読させる UI 文言を禁止。
- 本項が Portal-as-catalog を「機能」にするか「負債」にするかの分岐点である旨を
  `goal.md` safety requirements に追記する。

---

## 任意 — walking skeleton 先行（sequencing 提案）

PR-PPC-5b 直後に「static HTML をモバイルで Play → gateway preview」だけの薄い縦 slice を
一度通し、runtime + proxy を実機検証してから Capsule / Portal へ進む。
strict bottom-up のままでも可。リスク前倒し用の任意手順。

---

## 制約（既存指示書と同じ精神）

- すべて安全方向のみ。`workflow_state` / PlanPool authority / approval / critical event /
  allowed path / rollback / retry limit を緩めない。
- `main.py` / `ui.html` は必要最小の hook（lifespan への reconciliation 登録、Atlas header への
  Capsule/Play/Plan History 注入、`web/js/atlas_claude_panel.js` の `/play` intent 追加）以外は触らない。
  - 参考: `classifyIntent`（`web/js/atlas_claude_panel.js` 付近）は現状 `/plan` を prefix 判定し、
    `/play` は未対応。`/play` を追加しても `/plan` と衝突しないこと（`/play` が `show_plan_list` に
    誤分類されない）を test 化する。
- 未実行 test を成功扱いしない。各 PR は小さく独立して review 可能にする。

---

## 反映先まとめ

| 補正 | 主な反映先 | 対象 PR-PPC |
|---|---|---|
| C1 baseline / lifespan | `current_status.md`, `implementation_plan.md` | 0, 4, 11 |
| C2 threat model 分離 | `goal.md`, `implementation_plan.md` | 0 |
| C3 proxy 分割・ゲート | `implementation_plan.md` | 5 → 5a / 5b |
| C4 composite 実行 slice | `implementation_plan.md` | 4 / 新設 4b, 9 |
| C5 Windows cleanup | `implementation_plan.md` | 4, 11, 12 |
| O1 Console 再定義 | `atlas_play_spec.md`, `implementation_plan.md` | 6 |
| O2 free-form command 既知制限 | `goal.md`, `atlas_capsule_portal_spec.md` | 0, 7 |
| O3 Data Backup 合成性 | `atlas_capsule_portal_spec.md` | 10 |
| S1 untrusted 隔離方針 | `goal.md` safety requirements | 0（全 Run 経路に波及） |
