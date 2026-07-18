# KasaneCore UI刷新 詳細設計書 (ui_next)

作成日: 2026-07-19
親文書: `docs/ui_next_master_plan.md`

## 1. 成果物レイアウト

```
ui_next/
  index.html            # 新UIエントリ(build_ui_next.py が生成、シェル差し替え済み)
  css/
    tokens.css          # フォント/radius/影/モーション等の追加トークン(テーマ色はcore.jsのUI_THEMESが適用)
    next.css            # 新シェル+コンポーネント再スキン(最終読み込み・上書き層)
  js/
    core.js             # ui.html インラインJS抽出+最小パッチ適用済みコア
scripts/
  build_ui_next.py      # ui.html → ui_next/ 変換(再実行可能・冪等)
  smoke_ui_next_playwright.py  # 新UI用スモーク(Phase 2)
```

CSSの読み込み順: `/static/css/app.css`(レガシー共有・無改変)→ `tokens.css` → `next.css`。
フォークせず本家 app.css を直接参照する(重複を作らない。レガシー凍結後は事実上安定土台)。

## 2. 変換スクリプト build_ui_next.py の仕様

入力: `ui.html`(原本)。出力: `ui_next/index.html`, `ui_next/js/core.js`。

処理手順:
1. インラインscript(1ブロック、約680KB)を抽出し、下記「core.jsパッチ」を適用して `ui_next/js/core.js` へ書き出す。
2. `<head>` を新規生成:
   - フォント: Space Grotesk / Inter / JetBrains Mono(Google Fonts。レガシー同様CDN)
   - CSS: `/static/css/app.css` → `/ui-next/css/tokens.css` → `/ui-next/css/next.css`
   - marked CDN はレガシーと同一のものを維持
3. `<body>` 変換:
   - 旧 `<header>…</header>` ブロックを新シェルに置換:
     - `<aside class="side-nav">`: ロゴマーク + モードナビ(`id="btn-chat|btn-atlas|btn-echo|btn-nexus|btn-forge|btn-portal"`、class `mode-btn` 維持、inline SVGアイコン+ラベル)+ 下部に設定ボタン(`id="settings-btn"`)
     - `<div class="main-col">`: 先頭に薄い `<header class="topbar">`(`model-badge` / `sdot` / `stext` を収容)、以降は旧bodyコンテンツをそのまま内包
   - 上記以外のマークアップ(sys-usage-row / mob-tabs / app-body / 全モーダル)は**無改変で移植**(ID契約完全保存)
   - `.js-theme-select` の `<option>` 群を新テーマ名に置換
4. 外部scriptタグはそのまま(`/static/js/*.js` 共有)。インラインscriptは `<script src="/ui-next/js/core.js?v=…">` に置換。

### core.js パッチ(最小・機械的に適用)

| # | 対象 | 変更 | 理由 |
|---|---|---|---|
| P1 | `UI_THEMES` 定義 | 新3テーマに置換: `aurora`(既定: スレート+バイオレット/シアン)、`nocturne`(深藍)、`daylight`(ライト) | テーマ色はJSがinline styleで適用するため、CSSではなくここが色の源泉 |
| P2 | `THEME_STORAGE_KEY` | `'kc_theme'` → `'kc_theme_next'` | レガシーで保存済みの `cyber` 等が新UIの既定を汚染するのを防ぐ |
| P3 | `setTheme` のフォールバック / `initTheme` の既定 | `'cyber'` → `'aurora'`(旧テーマ名は `aurora` へマップ) | 既定テーマの刷新 |

シェル依存(調査済み・対応):
- `document.querySelector('header')` — 高さ計算(fallback 52px)→ 新シェルにも `<header>` が存在するため無変更で動作
- `document.querySelector('.app-body')` / `'.mob-tabs'` — 無改変移植のため動作
- `.mode-btn` への `active` クラストグル — サイドバーのボタンが同ID・同クラスを保持するため動作

## 3. 新シェル構造

```html
<body>
  <aside class="side-nav" id="side-nav">
    <div class="side-logo">◎ Kasane</div>
    <nav class="side-modes">
      <button class="mode-btn active" id="btn-chat"  onclick="setMode('chat')">…SVG… <span>Lumen</span></button>
      <button class="mode-btn" id="btn-atlas" onclick="setMode('atlas')">…SVG… <span>Atlas</span></button>
      <button class="mode-btn" id="btn-echo"  onclick="setMode('echo')">…SVG… <span>Echo</span></button>
      <button class="mode-btn" id="btn-nexus" onclick="setMode('nexus')">…SVG… <span>Nexus</span></button>
      <button class="mode-btn" id="btn-forge" onclick="setMode('forge')">…SVG… <span>Forge</span></button>
      <button class="mode-btn" id="btn-portal" onclick="setMode('portal')">…SVG… <span>Portal</span></button>
    </nav>
    <div class="side-bottom">
      <button class="hdr-icon-btn" id="settings-btn" onclick="openSettings()">…歯車SVG…</button>
    </div>
  </aside>
  <div class="main-col">
    <header class="topbar">
      <div class="topbar-title" id="topbar-mode-title"></div><!-- next.js側は使わずCSS装飾のみ。core無改変のため空でも可 -->
      <div class="hdr-right">(model-badge / sdot / stext — 旧IDそのまま)</div>
    </header>
    <div class="sys-usage-row">…旧のまま…</div>
    …旧bodyの残り全て(mob-tabs / app-body / モーダル群)…
  </div>
</body>
```

- デスクトップ: `body{display:flex;flex-direction:row}`、`.side-nav` 幅 76px(アイコン+極小ラベル)、`.main-col` が旧bodyのcolumnレイアウトを引き継ぐ。
- モバイル(≤768px): `.side-nav` 非表示、既存 `.mob-tabs`(下部タブ)を再スタイルして使用。

## 4. デザインシステム

### テーマパレット(core.js UI_THEMES)

- **aurora(既定)**: bg `#0b0d14→#232838` スレート階調 / text `#e9ecf5` / accent `#7c7cf5`(バイオレット)、glow系はシアン混じり
- **nocturne**: 深藍ベース / accent `#4cc2ff`
- **daylight**: ライト(`#f4f6fb` ベース / accent `#3d5af5`)

### tokens.css(テーマ非依存トークン)

```css
:root{
  --font-ui:'Inter','Hiragino Sans',sans-serif;
  --font-display:'Space Grotesk','Inter',sans-serif;
  --font-mono:'JetBrains Mono',monospace;
  --r:10px; --r2:14px;
  --shadow-1:0 1px 2px rgba(0,0,0,.25); --shadow-2:0 8px 28px rgba(0,0,0,.35);
  --ease:cubic-bezier(.2,.8,.2,1); --dur:.18s;
}
```

### next.css の担当範囲

1. 新シェル(side-nav / topbar / main-col / モバイル分岐)
2. コンポーネント再スキン: ボタン、タブ(`.tab-btn`/`.panel-tabs`)、カード(`.atlas-panel-card` 等)、入力欄(`.input-wrap`/textarea/select)、モーダル、スクロールバー、バッジ、チャットバブル(`.msg-bubble`)
3. モーション: hover/active遷移、フォーカスリング、`prefers-reduced-motion` 対応
4. 未上書き領域は app.css の旧スタイルのまま表示される(機能は無傷)= 段階的に洗練可能な安全設計

## 5. 配信・切替設計(main.py)

```python
UI_NEXT_DIR = os.path.join(BASE_DIR, "ui_next")
_ui_variant = os.environ.get("KASANE_UI_VARIANT", "next")  # Phase 1では "legacy"、Phase 3で "next"

@app.get("/")
def root():
    if _ui_variant != "legacy" and os.path.exists(os.path.join(UI_NEXT_DIR, "index.html")):
        return FileResponse(ui_next_index, media_type="text/html", headers=no_store)
    return serve_existing_ui_index()
```

- `app.mount("/ui-next", StaticFiles(ui_next, html=True))` を `configure_static_assets` に追加(`ui_next_dir` 引数、無ければ従来動作)。
- `/ui/`(レガシー静的)と `/ui-next/`(新)は変数に関係なく常時アクセス可能。
- ロールバック: `KASANE_UI_VARIANT=legacy` で即時旧UI復帰。

## 6. 検証設計

1. **構文検証**: `node --check` 相当は使わず、`scripts/check_ui_inline_script_syntax.py` と同等のesprima系チェックを core.js に流用(または python -c での簡易検査+ブラウザコンソール確認)
2. **スモーク(自動)**: `scripts/smoke_ui_next_playwright.py` — `/ui-next/` を開き、6モードを順に `setMode` 相当のクリックで遷移、各モードの主要ルート要素が表示されること・コンソールエラーが無いことを確認。スクリーンショットを `artifacts/playwright/` に保存
3. **ライブ検証**: :8000 の実サーバーで手動確認(チャット送信、設定モーダル、プロジェクトドロワー、各パネルタブ)
4. **回帰**: `pytest tests/`(レガシー契約68+75本を含む)全緑

## 7. 実装順序

1. `scripts/build_ui_next.py` + 生成物(構造のみ・旧スタイル表示)
2. サーバーに `/ui-next/` マウント追加(Phase 1: `/` はレガシーのまま)
3. tokens.css / next.css / UI_THEMES 刷新(デザイン実装)
4. スモーク作成・実行 → ライブ検証
5. Phase 3 切替(`/` 既定を next に、README更新)
