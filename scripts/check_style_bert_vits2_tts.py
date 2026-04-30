#!/usr/bin/env python3
"""Style-Bert-VITS2 TTS wiring check.

目的:
- Style-Bert-VITS2 ランタイムが音声合成可能かを最小確認
- UI の自動TTS / メッセージ右下再生ボタンの経路が style_bert_vits2 に到達するか確認

このスクリプトはネットワーク不要・モデル不要で、実装状態を静的/軽量に判定する。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.tts.style_bert_vits2_runtime import StyleBertVITS2Runtime

UI_PATH = ROOT / "ui.html"


def main() -> int:
    ui_text = UI_PATH.read_text(encoding="utf-8")
    runtime = StyleBertVITS2Runtime()

    report: dict[str, object] = {
        "runtime_engine_key": runtime.engine_key,
        "runtime_status": runtime.status(),
        "ui_has_auto_tts_toggle": "id=\"tts-auto-chk\"" in ui_text,
        "ui_has_message_play_button_handler": "function ttsSpeakMsg(btn)" in ui_text,
        "ui_routes_style_bert_vits2_to_synthesize_api": "engine === 'style_bert_vits2'" in ui_text
        and "fetch(API + '/tts/synthesize'" in ui_text,
        "ui_has_no_tts_engine_label": "TTS Engine" not in ui_text,
        "ui_has_no_use_tts_translation_label": "Use TTS Translation" not in ui_text,
        "ui_has_no_extra_text_process_options": "Extra Text Process Options" not in ui_text,
        "ui_has_no_jp_extra_text_process_options": "JP Extra Text Process Options" not in ui_text,
        "ui_has_no_jp_extra_non_japanese_policy": "JP Extra Non Japanese Policy" not in ui_text,
        "result": "unknown",
        "detail": "",
    }

    try:
        runtime.synthesize({"text": "テスト", "engine": "style_bert_vits2", "model": "dummy"})
        report["result"] = "ready"
        report["detail"] = "Style-Bert-VITS2 synthesize() succeeded."
    except Exception as exc:  # 実装状態の確認目的
        report["result"] = "not_ready"
        report["detail"] = f"{type(exc).__name__}: {exc}"

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["result"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
