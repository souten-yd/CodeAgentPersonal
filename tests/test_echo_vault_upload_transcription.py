import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main


class EchoVaultUploadTranscriptionTests(unittest.TestCase):
    def test_import_audio_transcript_generates_segmented_transcript(self):
        text = "今日は会議を開始します。次に進捗を確認します。最後に課題を整理します。"
        with tempfile.TemporaryDirectory() as td:
            with patch.object(main, "ECHOVAULT_DIR", td), patch.object(main, "_echo_do_translate", side_effect=lambda t, **_: f"EN:{t}"):
                out = main.echo_import_audio_transcript({
                    "transcript_text": text,
                    "language": "ja",
                    "original_filename": "demo.wav",
                })

            self.assertTrue(out["ok"])
            base = out["session"]
            self.assertEqual(out["transcript_raw_filename"], f"{base}_transcript_raw.txt")
            self.assertEqual(out["transcript_segments_filename"], f"{base}_transcript_segments.json")
            seg_path = Path(td) / f"{base}_transcript_segments.json"
            self.assertTrue(seg_path.exists())
            segs = json.loads(seg_path.read_text(encoding="utf-8"))
            self.assertEqual(len(segs), 3)
            self.assertTrue(all("index" in s and "start" in s and "end" in s and "source_text" in s for s in segs))
            self.assertTrue(all("detected_language" in s and "japanese_text" in s and "english_text" in s and "warnings" in s for s in segs))

            transcript_md = (Path(td) / out["transcript_filename"]).read_text(encoding="utf-8")
            self.assertGreaterEqual(transcript_md.count("\n| 1 |"), 1)
            self.assertIn("今日は会議を開始します。", transcript_md)
            self.assertIn("次に進捗を確認します。", transcript_md)
            self.assertIn("最後に課題を整理します。", transcript_md)

    def test_long_english_without_punctuation_is_split_by_max_chars(self):
        text = " ".join(["word"] * 120)
        with tempfile.TemporaryDirectory() as td:
            with patch.object(main, "ECHOVAULT_DIR", td), patch.object(main, "_echo_do_translate", side_effect=lambda t, **_: f"JA:{t}"):
                out = main.echo_import_audio_transcript({
                    "transcript_text": text,
                    "language": "en",
                })

            seg_path = Path(td) / f"{out['session']}_transcript_segments.json"
            segs = json.loads(seg_path.read_text(encoding="utf-8"))
            self.assertGreater(len(segs), 1)
            self.assertTrue(all(len(s["source_text"]) <= 170 for s in segs))

    def test_translation_failure_warning_is_recorded(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.object(main, "ECHOVAULT_DIR", td), patch.object(main, "_echo_do_translate", return_value="[翻訳エラー: timeout]"):
                out = main.echo_import_audio_transcript({
                    "transcript_text": "今日は検証です。",
                    "language": "ja",
                })
            segs = json.loads((Path(td) / out["transcript_segments_filename"]).read_text(encoding="utf-8"))
            self.assertIn("translation_failed", segs[0]["warnings"])
            self.assertEqual(out["translation_warning_count"], 1)

    def test_mixed_language_segments_are_detected_per_piece(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.object(main, "ECHOVAULT_DIR", td), patch.object(main, "_echo_do_translate", side_effect=lambda t, **_: f"T:{t}"):
                out = main.echo_import_audio_transcript({
                    "transcript_text": "fallback",
                    "language": "ja",
                    "segments": [
                        {"start": 0, "end": 4, "text": "今日は晴れです。"},
                        {"start": 4, "end": 8, "text": "Next we review the roadmap."},
                    ],
                })
            segs = json.loads((Path(td) / out["transcript_segments_filename"]).read_text(encoding="utf-8"))
            langs = [s["detected_language"] for s in segs]
            self.assertIn("ja", langs)
            self.assertIn("en", langs)

    def test_segment_times_are_distributed_when_split(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.object(main, "ECHOVAULT_DIR", td), patch.object(main, "_echo_do_translate", side_effect=lambda t, **_: f"EN:{t}"):
                out = main.echo_import_audio_transcript({
                    "transcript_text": "A. B. C.",
                    "language": "en",
                    "segments": [{"start": 0.0, "end": 12.0, "text": "A. B. C."}],
                })
            segs = json.loads((Path(td) / out["transcript_segments_filename"]).read_text(encoding="utf-8"))
            self.assertEqual(len(segs), 3)
            self.assertAlmostEqual(segs[0]["start"], 0.0, places=2)
            self.assertGreater(segs[1]["start"], segs[0]["start"])
            self.assertGreater(segs[2]["start"], segs[1]["start"])
            self.assertAlmostEqual(segs[-1]["end"], 12.0, places=2)

    def test_ja_hint_still_splits_english_segment_by_period(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.object(main, "ECHOVAULT_DIR", td), patch.object(main, "_echo_do_translate", side_effect=lambda t, **_: f"T:{t}"):
                out = main.echo_import_audio_transcript({
                    "transcript_text": "fallback",
                    "language": "ja",
                    "segments": [{"start": 0, "end": 8, "text": "Next we review the roadmap. Then we check the risks."}],
                })
            segs = json.loads((Path(td) / out["transcript_segments_filename"]).read_text(encoding="utf-8"))
            self.assertEqual(len(segs), 2)
            self.assertEqual([s["source_text"] for s in segs], ["Next we review the roadmap.", "Then we check the risks."])

    def test_en_hint_still_splits_japanese_segment_by_japanese_period(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.object(main, "ECHOVAULT_DIR", td), patch.object(main, "_echo_do_translate", side_effect=lambda t, **_: f"T:{t}"):
                out = main.echo_import_audio_transcript({
                    "transcript_text": "fallback",
                    "language": "en",
                    "segments": [{"start": 0, "end": 8, "text": "最初に確認します。次にリスクを見ます。"}],
                })
            segs = json.loads((Path(td) / out["transcript_segments_filename"]).read_text(encoding="utf-8"))
            self.assertEqual(len(segs), 2)
            self.assertEqual([s["source_text"] for s in segs], ["最初に確認します。", "次にリスクを見ます。"])

    def test_ui_does_not_list_artifact_labels_for_upload_completion(self):
        ui = Path("ui.html").read_text(encoding="utf-8")
        self.assertNotIn("Segments JSON", ui)
        self.assertNotIn("Japanese transcript", ui)
        self.assertNotIn("English transcript", ui)
        self.assertNotIn("Bilingual minutes", ui)

    def test_sessions_api_skips_helper_artifacts(self):
        with tempfile.TemporaryDirectory() as td:
            base = "2026-04-30_16-10_upload_demo"
            (Path(td) / f"{base}_transcript_segments.json").write_text("[]", encoding="utf-8")
            (Path(td) / f"{base}_transcript_ja.txt").write_text("ja", encoding="utf-8")
            (Path(td) / f"{base}_transcript_en.txt").write_text("en", encoding="utf-8")
            (Path(td) / f"{base}_minutes_bilingual.md").write_text("# Minutes", encoding="utf-8")
            (Path(td) / f"{base}_transcript.md").write_text("# 文字起こし", encoding="utf-8")
            with patch.object(main, "ECHOVAULT_DIR", td):
                out = main.echo_list_sessions()
            names = [f["name"] for f in out["files"]]
            self.assertEqual(names, [f"{base}_transcript.md"])

    def test_generate_minutes_separates_japanese_and_english_sections(self):
        with tempfile.TemporaryDirectory() as td:
            transcript_name = "2026-04-30_16-10_upload_demo_transcript.md"
            md = "\n".join([
                "# 文字起こし — demo",
                "",
                "| # | 言語 | 原文 |",
                "|---|------|------|",
                "| 1 | 🇯🇵 | こんにちは。 |",
                "| 2 | 🇺🇸 | Today we review the plan. |",
            ])
            (Path(td) / transcript_name).write_text(md, encoding="utf-8")
            with patch.object(main, "ECHOVAULT_DIR", td), patch.object(main, "_echo_do_translate", side_effect=lambda t, **_: f"T:{t}"):
                out = main.echo_generate_minutes({"transcript_filename": transcript_name, "overwrite": True})
            minutes = (Path(td) / out["filename"]).read_text(encoding="utf-8")
            self.assertLess(minutes.index("## 日本語"), minutes.index("## English"))
            self.assertNotIn(" / ", minutes)


if __name__ == "__main__":
    unittest.main()
