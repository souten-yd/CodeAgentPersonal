# Codex 実装指示書: 視覚コントラクト false-negative 修正（色名 keyframes / motion 過剰必須）

## 目的（なぜやるか）

「Hello world をレインボーに自動変化させる HTML」を autopilot に投げると、生成物は**完全に正しい**のに `verification_failed:visual_contract_failed` で停止する。原因は生成物ではなく **static 視覚コントラクト（`agent/atlas_visual_artifact_verifier.py`）の 2 つの false-negative**：

1. **color_mutation_signal が CSS 色名を認識しない** — 生成 HTML は `@keyframes rainbow { 0%{color:red} 20%{color:orange} ... }` のように**色名**で色を変化させるが、`_COLOR_SIGNALS` は `hsl()/rgb()/style.color/--*color:/hue-rotate` のみを見るため「色変化なし」と誤判定。
2. **motion_signal を全アニメ課題で必須化** — 今回の要件は「文字色の変化」で**動きは不要**。なのに motion を必須にしているため落ちる。

### 実測の裏付け（この通り直ればよい）

対象成果物 `index.html`（要件を満たしている）:
```html
<style>
  .hello-world { font-size: 3rem; animation: rainbow 3s infinite; }
  @keyframes rainbow {
    0% { color: red; } 20% { color: orange; } 40% { color: yellow; }
    60% { color: green; } 80% { color: blue; } 100% { color: purple; }
  }
</style>
<div class="hello-world">Hello World</div>
```

`verification_result.metadata.visual_contract`（失敗時の実出力）:
```json
{ "status": "failed",
  "checks": [
    {"check":"animation_signal","status":"passed","detail":"css_keyframes"},
    {"check":"color_mutation_signal","status":"failed","detail":null},
    {"check":"motion_signal","status":"failed","detail":null}],
  "missing": ["color_mutation_signal","motion_signal"] }
```

加えて `browser_smoke` が `{"status":"browser_smoke_failed","reason":"playwright_error: "}`（**本文が空**）。つまりブラウザ smoke も別要因で落ちており、PR #1565 の「smoke passed なら static を override」も効かない。よって **static 検証器自体を直す**のが本筋（ブラウザ非依存で正しい成果物を通せる）。

## ゴール

- 上記 `index.html`（色名 keyframes・動き無し）が **static コントラクトを pass** する（ブラウザ不要）。
- ただし **コントラクトを弱めない**：本当に動きが要件の課題（"move/animate movement" 等）で motion が無ければ従来どおり fail。色が要件なのに色変化が無ければ fail。
- `agent/atlas_playwright_smoke_verifier.py` の空 `playwright_error:` を診断可能にする（例外型名を含める）。

## 非ゴール

- ブラウザ smoke が空エラーで落ちる**根本原因**の解明（Windows での launch 失敗）は本タスク対象外。本タスクは「型名を出して診断可能にする」までで、原因調査は別途。
- PR #1565 の runtime-override ロジックの変更はしない（併存させる）。

---

## 対象コードと現状（file:line）

`agent/atlas_visual_artifact_verifier.py`
- `_ANIMATION_SIGNALS`（`9-12`）, `_COLOR_SIGNALS`（`13-19`）, `_MOTION_SIGNALS`（`20-24`）, `_WAVE_PHASE_SIGNALS`（`25-31`）。
- `_ANIMATION_TASK_KEYWORDS`（`34-37`）, `_WAVE_TASK_KEYWORDS`（`38-41`）。
- `verify_static()`（`51-129`）：`is_animation_task` のとき **animation/color/motion を全て必須**にしている（`74-108`）。色/動きは `_check_signals()`（`131`）で検出。
- `_check_signals(content, signals)`：最初にマッチした signal の detail 文字列を返す。

`agent/atlas_playwright_smoke_verifier.py`
- 例外ハンドラ（`154-156` 付近、PR #1565 後は `_is_browser_not_installed_error` 分岐の直後）：`return self._result("browser_smoke_failed", reason=f"playwright_error: {exc}", ...)`。`str(exc)` が空だと `playwright_error: `（本文空）になる。

---

## 実装計画（タスク・チェックリスト）

このファイルが唯一の正典。各タスク完了ごとにチェックを更新してコミットすること。

### A. static 検証器: タスク連動の必須判定 + 色名 keyframes 認識
- [x] A-1: `_COLOR_TASK_KEYWORDS` / `_MOTION_TASK_KEYWORDS` を追加（下記）。
- [x] A-2: `_keyframe_color_mutation(content) -> str | None` を追加：`@keyframes` ブロックを brace スキャンで切り出し、内部に **`color:` / `background-color:` の異なる値が 2 つ以上**あれば色変化と判定（色名でも検出できる）。
- [x] A-3: `verify_static` の color/motion 判定を **タスク連動の required/advisory** に変更：
  - `color_mutation_signal`：`is_animation_task and wants_color` のときのみ必須。検出は `_check_signals(_COLOR_SIGNALS) or _keyframe_color_mutation(content)`。
  - `motion_signal`：`is_animation_task and wants_motion` のときのみ必須。
  - **ベースライン**：`is_animation_task` かつ color も motion も要件語に無い汎用課題で、color も motion も検出されない場合のみ `visual_change_signal` を missing に積む（＝何も変化しないアニメは fail。弱体化防止）。
- [x] A-4: 既存テスト（`tests/test_atlas_visual_artifact_verifier.py`）が**全て緑のまま**であることを確認（下記「テスト互換性」を必読）。

### B. smoke 診断改善
- [x] B-1: `atlas_playwright_smoke_verifier.py` の例外ハンドラで `reason=f"playwright_error: {type(exc).__name__}: {exc}"`（末尾の `: ` は trim）に変更。`playwright_error:` プレフィックスは維持（hard/soft 分類・既存 startswith 消費者を壊さない）。

### C. テスト + 受け入れ
- [x] C-1: 新規テストを追加（下記「追加テスト」）。
- [x] C-2: 既存スイート（visual_artifact / auto_verification / pr9_visual_depth / playwright_smoke）緑。
- [x] C-3: 受け入れ基準を満たす。

---

## 実装詳細

### A-1 追加キーワード

```python
_COLOR_TASK_KEYWORDS = re.compile(r'\b(colou?r|hue|rainbow|gradient|chromat|tint|palette|spectrum)', re.IGNORECASE)
_MOTION_TASK_KEYWORDS = re.compile(
    r'\b(mov\w*|motion|wave|oscillat|bounce|spin\w*|rotat\w*|slide|drift|orbit|translat\w*|scroll|fall\w*|jump\w*|fly\w*|shake|swing)',
    re.IGNORECASE,
)
```

### A-2 色名対応の keyframe 検出

```python
def _keyframe_color_mutation(self, content: str) -> str | None:
    """@keyframes 内に異なる color/background-color 宣言が2つ以上あれば色変化とみなす。
    CSS 色名（red/orange/...）でも検出できる（_COLOR_SIGNALS の hsl/rgb 限定を補完）。"""
    for m in re.finditer(r'@keyframes\s+[\w-]+\s*\{', content, re.IGNORECASE):
        start = m.end() - 1  # '{' の位置
        depth = 0
        block = content[start:]
        for i in range(start, len(content)):
            if content[i] == '{':
                depth += 1
            elif content[i] == '}':
                depth -= 1
                if depth == 0:
                    block = content[start:i + 1]
                    break
        values = re.findall(r'(?:background-)?color\s*:\s*([^;}\n]+)', block, re.IGNORECASE)
        if len({v.strip().lower() for v in values}) >= 2:
            return 'keyframe_color_mutation'
    return None
```

### A-3 verify_static の判定差し替え（color/motion 部分）

`is_animation_task` 算出の直後に `wants_color`/`wants_motion` を足し、color(2.)・motion(3.) ブロックを次の方針で置換：

```python
wants_color = bool(_COLOR_TASK_KEYWORDS.search(task_desc))
wants_motion = bool(_MOTION_TASK_KEYWORDS.search(task_desc))

def _record(name, found, required):
    if found:
        checks.append({"check": name, "status": "passed", "detail": found})
    elif required:
        checks.append({"check": name, "status": "failed", "detail": None})
        missing.append(name)
    else:
        checks.append({"check": name, "status": "advisory", "detail": None})

color_found = self._check_signals(content, _COLOR_SIGNALS) or self._keyframe_color_mutation(content)
motion_found = self._check_signals(content, _MOTION_SIGNALS)
_record("color_mutation_signal", color_found, required=is_animation_task and wants_color)
_record("motion_signal", motion_found, required=is_animation_task and wants_motion)
if is_animation_task and not wants_color and not wants_motion and not (color_found or motion_found):
    checks.append({"check": "visual_change_signal", "status": "failed", "detail": None})
    missing.append("visual_change_signal")
```

`animation_signal`（1.）と `wave_phase_signal`（4.）の既存ロジックはそのまま。

---

## テスト互換性（破ってはならない既存テスト・設計の根拠）

`tests/test_atlas_visual_artifact_verifier.py` の既存挙動と矛盾しないこと。設計はこれらを満たすよう導出済み：

- `test_html_with_text_but_no_color_mutation_fails_animation_task`（task=`animate colors`）→ wants_color=True・色なし → **color 必須で missing → fail**（維持）。
- `test_html_with_color_but_no_motion_fails_animation_task`（task=`animate movement`）→ wants_motion=True（`mov`）・motion なし → **motion 必須で missing → fail**（維持）。色は present だが required=False なので advisory/passed 扱い。
- `test_html_file_existence_alone_fails_for_animation_task`（task=`animate color wave`）→ wants_color/wants_motion 両 True・全欠落 → fail（維持）。
- `test_valid_animation_html_passes_static_contract`（task=`animate color wave with sine oscillation`）→ 全 present → pass、color/motion/wave が passed_checks に含まれる（維持）。
- `test_non_animation_task_treats_missing_signals_as_advisory` → 非アニメ課題は advisory（維持）。
- multifile 系（task=`animate color motion ...`）→ color/motion 両 present → pass、空/traversal は animation 欠落で fail（維持）。

## 追加テスト（`tests/test_atlas_visual_artifact_verifier.py` に追記）

```python
_RAINBOW_NAMED_COLORS_HTML = """\
<!doctype html><html><head><style>
.hello-world { animation: rainbow 3s infinite; }
@keyframes rainbow { 0%{color:red} 20%{color:orange} 40%{color:yellow}
 60%{color:green} 80%{color:blue} 100%{color:purple} }
</style></head><body><div class="hello-world">Hello World</div></body></html>
"""

def test_named_color_keyframes_satisfy_color_mutation(tmp_path):
    f = tmp_path / 'index.html'; f.write_text(_RAINBOW_NAMED_COLORS_HTML, encoding='utf-8')
    r = _VFY.verify_static(f, task_description='display text that cycles through rainbow colors')
    assert r['status'] == 'passed', r
    assert 'color_mutation_signal' not in r['missing']
    assert 'motion_signal' not in r['missing']   # 色課題に動きは不要

def test_color_task_does_not_require_motion(tmp_path):
    f = tmp_path / 'index.html'; f.write_text(_RAINBOW_NAMED_COLORS_HTML, encoding='utf-8')
    r = _VFY.verify_static(f, task_description='rainbow color animation')
    assert r['status'] == 'passed'

def test_movement_task_still_requires_motion(tmp_path):
    # 動きが要件なら従来どおり motion 必須（弱体化していないことの確認）
    f = tmp_path / 'index.html'; f.write_text(_RAINBOW_NAMED_COLORS_HTML, encoding='utf-8')
    r = _VFY.verify_static(f, task_description='make the text bounce and move around')
    assert r['status'] == 'failed'
    assert 'motion_signal' in r['missing']
```

（smoke 診断 B のテストは `tests/test_atlas_playwright_smoke_verifier.py` に「例外型名が reason に含まれる」アサートを追加。）

---

## 受け入れ基準（Acceptance）

- [x] 実測の `index.html`（色名 keyframes・動き無し）が `verify_static` で **passed**。
- [x] 色が要件なのに色変化が無い HTML は従来どおり fail。動きが要件なのに動きが無い HTML は従来どおり fail。
- [x] `tests/test_atlas_visual_artifact_verifier.py` の既存テストが全緑＋追加テスト緑。
- [x] `agent/atlas_playwright_smoke_verifier.py` の空 `playwright_error:` が例外型名を含むようになる。
- [x] auto_verification / pr9_visual_depth 等の関連スイート緑。PR #1565 の override ロジックは不変。

## 実装順序 / コミット

1. A（static 検証器）→ 既存緑確認 → 追加テスト緑。
2. B（smoke 診断）→ テスト緑。

各コミットは対象と理由を明記。**PR 作成・マージはユーザーの明示指示があるまで行わない。**
