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


if __name__ == "__main__":
    unittest.main()
