import unittest
from types import SimpleNamespace
from unittest.mock import patch
import sys

from app.nexus.downloader import _build_ssl_context


class NexusDownloaderTests(unittest.TestCase):
    def test_build_ssl_context_uses_certifi_cafile(self) -> None:
        fake_certifi = SimpleNamespace(where=lambda: "/tmp/certifi.pem")
        with patch.dict(sys.modules, {"certifi": fake_certifi}), patch(
            "app.nexus.downloader.ssl.create_default_context"
        ) as mocked_ctx:
            _build_ssl_context()
        mocked_ctx.assert_called_once_with(cafile="/tmp/certifi.pem")


if __name__ == "__main__":
    unittest.main()
