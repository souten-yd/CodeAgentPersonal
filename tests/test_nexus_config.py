import os
import unittest
from unittest.mock import patch

from app.nexus.config import load_runtime_config


class NexusConfigRuntimeTests(unittest.TestCase):
    def test_default_searxng_url_uses_localhost_when_runpod_runtime_forced(self) -> None:
        with patch.dict(
            os.environ,
            {
                "CODEAGENT_RUNTIME": "runpod",
                "NEXUS_SEARXNG_URL": "",
                "RUNPOD_POD_ID": "",
                "RUNPOD_API_KEY": "",
            },
            clear=False,
        ):
            with patch("app.nexus.config.Path.exists", return_value=True):
                cfg = load_runtime_config()

        self.assertEqual(cfg.searxng_url, "http://127.0.0.1:8088")

    def test_parallel_download_config_defaults_and_minimums(self) -> None:
        with patch.dict(
            os.environ,
            {
                "NEXUS_DOWNLOAD_CONCURRENCY": "0",
                "NEXUS_PDF_EXTRACT_CONCURRENCY": "-1",
                "NEXUS_DOWNLOAD_PROGRESS_INTERVAL_SEC": "0",
                "NEXUS_DOWNLOAD_STALLED_AFTER_SEC": "0",
            },
            clear=False,
        ):
            cfg = load_runtime_config()

        self.assertEqual(cfg.download_concurrency, 1)
        self.assertEqual(cfg.pdf_extract_concurrency, 1)
        self.assertEqual(cfg.download_progress_interval_sec, 1)
        self.assertEqual(cfg.download_stalled_after_sec, 1)


if __name__ == "__main__":
    unittest.main()
