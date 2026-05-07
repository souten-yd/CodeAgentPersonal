import unittest

import main

from tests.helpers.ui_contract import load_ui_contract_text


class WebSearchSettingsDefaultsTests(unittest.TestCase):
    def test_search_enabled_default_is_true(self) -> None:
        self.assertEqual(main.SETTINGS_DEFAULTS.get("search_enabled"), "true")

    def test_resolve_effective_search_enabled_defaults_to_runtime_flag(self) -> None:
        original = main._search_enabled
        try:
            main._search_enabled = True
            self.assertTrue(main._resolve_effective_search_enabled(None))
            main._search_enabled = False
            self.assertFalse(main._resolve_effective_search_enabled(None))
            self.assertFalse(main._resolve_effective_search_enabled(False))
        finally:
            main._search_enabled = original


class WebSearchUiTextTests(unittest.TestCase):
    def test_ui_removes_legacy_duckduckgo_label(self) -> None:
        html = load_ui_contract_text()
        self.assertNotIn("DuckDuckGo検索", html)

    def test_ui_removes_old_web_search_description(self) -> None:
        html = load_ui_contract_text()
        self.assertNotIn("必要と判断したときだけエージェントがWeb検索を使用", html)

    def test_ui_uses_nexus_web_status_fields(self) -> None:
        html = load_ui_contract_text()
        self.assertIn("active_provider", html)
        self.assertIn("provider", html)
        self.assertIn("search-provider-status", html)


if __name__ == "__main__":
    unittest.main()
