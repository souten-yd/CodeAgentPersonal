import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main


class EchoVaultUploadTranscriptionTests(unittest.TestCase):
    def test_import_audio_transcript_generates_segmented_artifacts_and_minutes_layout(self):
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
            seg_path = Path(td) / f"{base}_transcript_segments.json"
            self.assertTrue(seg_path.exists())
            segs = json.loads(seg_path.read_text(encoding="utf-8"))
            self.assertEqual(len(segs), 3)
            self.assertTrue(all("start" in s and "end" in s and "source_text" in s for s in segs))
            self.assertTrue(all("japanese_text" in s and "english_text" in s for s in segs))

            minutes = (Path(td) / f"{base}_minutes_bilingual.md").read_text(encoding="utf-8")
            self.assertLess(minutes.index("## 日本語"), minutes.index("## English"))
            self.assertNotIn(" / ", minutes)

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


if __name__ == "__main__":
    unittest.main()
