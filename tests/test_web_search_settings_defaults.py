import unittest

import main


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
        html = open("ui.html", "r", encoding="utf-8").read()
        self.assertNotIn("DuckDuckGo検索", html)

    def test_ui_removes_old_web_search_description(self) -> None:
        html = open("ui.html", "r", encoding="utf-8").read()
        self.assertNotIn("必要と判断したときだけエージェントがWeb検索を使用", html)

    def test_ui_uses_nexus_web_status_fields(self) -> None:
        html = open("ui.html", "r", encoding="utf-8").read()
        self.assertIn("active_provider", html)
        self.assertIn("provider", html)
        self.assertIn("search-provider-status", html)


if __name__ == "__main__":
    unittest.main()
