import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main


class EchoAlwaysBilingualTranslationTests(unittest.TestCase):
    def test_detect_language_prefers_text_over_hint(self):
        self.assertEqual(main._echo_detect_language_light("Today is a test.", "ja"), "en")
        self.assertEqual(main._echo_detect_language_light("今日はテストです。", "en"), "ja")
        self.assertEqual(main._echo_detect_language_light("OK", "ja"), "en")
        self.assertEqual(main._echo_detect_language_light("", "en"), "en")
        self.assertEqual(main._echo_detect_language_light("", "auto"), "ja")

    def test_ja_input_translates_to_en(self):
        calls = []

        def _fake_translate(text, source_language=None, target_language=None, llm_url=""):
            calls.append((source_language, target_language, text))
            return "Today is a test."

        with patch.object(main, "_echo_do_translate", side_effect=_fake_translate):
            out = main._echo_translate_opposite_language("今日はテストです。", "ja")

        self.assertEqual(out["source_language"], "ja")
        self.assertEqual(out["translated_language"], "en")
        self.assertEqual(out["english_text"], "Today is a test.")
        self.assertEqual(calls[0][0], "ja")
        self.assertEqual(calls[0][1], "en")

    def test_en_input_translates_to_ja(self):
        calls = []

        def _fake_translate(text, source_language=None, target_language=None, llm_url=""):
            calls.append((source_language, target_language, text))
            return "今日はテストです。"

        with patch.object(main, "_echo_do_translate", side_effect=_fake_translate):
            out = main._echo_translate_opposite_language("Today is a test.", "en")

        self.assertEqual(out["source_language"], "en")
        self.assertEqual(out["translated_language"], "ja")
        self.assertEqual(out["japanese_text"], "今日はテストです。")
        self.assertEqual(calls[0][0], "en")
        self.assertEqual(calls[0][1], "ja")

    def test_en_text_with_ja_hint_still_translates_to_ja_target(self):
        calls = []

        def _fake_translate(text, source_language=None, target_language=None, llm_url=""):
            calls.append((source_language, target_language, text))
            return "今日はテストです。"

        with patch.object(main, "_echo_do_translate", side_effect=_fake_translate):
            out = main._echo_translate_opposite_language("Today is a test.", "ja")

        self.assertEqual(out["source_language"], "en")
        self.assertEqual(out["translated_language"], "ja")
        self.assertEqual(calls[0][0], "en")
        self.assertEqual(calls[0][1], "ja")

    def test_ja_text_with_en_hint_still_translates_to_en_target(self):
        with patch.object(main, "_echo_do_translate", return_value="Today is a test.") as mocked:
            out = main._echo_translate_opposite_language("今日はテストです。", "en")
        self.assertEqual(out["source_language"], "ja")
        self.assertEqual(out["translated_language"], "en")
        mocked.assert_called_once()

    def test_translation_failure_sets_warning(self):
        with patch.object(main, "_echo_do_translate", return_value="[翻訳エラー: timeout]"):
            out = main._echo_translate_opposite_language("今日はテストです。", "ja")
        self.assertFalse(out["translation_used"])
        self.assertTrue(out["translation_failed"])
        self.assertIn("translation_failed", out["warnings"])

    def test_translate_exception_is_swallowed_and_source_text_is_kept(self):
        with patch.object(main, "_echo_do_translate", side_effect=RuntimeError("boom")):
            out = main._echo_translate_opposite_language("Today is a test.", "en")
        self.assertFalse(out["translation_used"])
        self.assertTrue(out["translation_failed"])
        self.assertIn("translation_failed", out["warnings"])
        self.assertEqual(out["translated_text"], "[translation failed]")
        self.assertEqual(out["english_text"], "Today is a test.")
        self.assertEqual(out["japanese_text"], "")

    def test_ui_tts_fallback_does_not_use_translation_failed_placeholder(self):
        ui = Path("ui.html").read_text(encoding="utf-8")
        self.assertIn("translatedFailed = sentence?.translation_failed === true", ui)
        self.assertIn("ttsText === '[translation failed]'", ui)
        self.assertIn("translated !== '[translation failed]'", ui)

    def test_import_audio_transcript_generates_bilingual_fields_via_common_function(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.object(main, "ECHOVAULT_DIR", td), patch.object(main, "_echo_do_translate", side_effect=lambda t, **_: f"TR:{t}"):
                out = main.echo_import_audio_transcript({"transcript_text": "Today is a test.", "language": "en"})
            segs = __import__("json").loads((Path(td) / out["transcript_segments_filename"]).read_text(encoding="utf-8"))
            self.assertIn("japanese_text", segs[0])
            self.assertIn("english_text", segs[0])

    def test_generate_minutes_separate_sections(self):
        with tempfile.TemporaryDirectory() as td:
            transcript_name = "2026-04-30_16-10_upload_demo_transcript.md"
            md = "\n".join([
                "# 文字起こし — demo",
                "",
                "| # | 言語 | 原文 |",
                "|---|------|------|",
                "| 1 | 🇯🇵 | こんにちは。 |",
                "| 2 | 🇺🇸 | Today is a test. |",
            ])
            (Path(td) / transcript_name).write_text(md, encoding="utf-8")
            with patch.object(main, "ECHOVAULT_DIR", td), patch.object(main, "_echo_do_translate", side_effect=lambda t, **_: f"T:{t}"):
                out = main.echo_generate_minutes({"transcript_filename": transcript_name, "overwrite": True})
            minutes = (Path(td) / out["filename"]).read_text(encoding="utf-8")
            self.assertLess(minutes.index("## 日本語"), minutes.index("## English"))
            self.assertNotIn(" / ", minutes)


if __name__ == "__main__":
    unittest.main()
