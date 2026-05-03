import re
import unittest
from pathlib import Path


class TestPhase21_6AtlasVisibilityRegressionUiContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ui = Path("ui.html").read_text(encoding="utf-8")

    def test_atlas_button_exists_and_wires_set_mode(self):
        self.assertIn('id="btn-atlas"', self.ui)
        self.assertIn("onclick=\"setMode('atlas')\"", self.ui)
        self.assertIn("['chat','atlas','agent','echo','nexus']", self.ui)

    def test_atlas_panel_and_core_ui_exist(self):
        for token in [
            'id="atlas-panel-col"',
            'id="atlas-workbench-card"',
            "Atlas Workbench",
            ">Overview<",
            ">Plan<",
            ">Runs<",
            ">Dashboard<",
            ">Patch Review<",
            ">Legacy<",
            ">Start Atlas<",
        ]:
            self.assertIn(token, self.ui)

    def test_setmode_atlas_shows_panel_and_restores_safely(self):
        m = re.search(r"else if \(m === 'atlas'\) \{([\s\S]*?)\n  \} else if \(m === 'nexus'\)", self.ui)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("atlasPanelCol.style.display = ''", body)
        self.assertIn("restoreAtlasSubviewState();", body)
        self.assertIn("try {", body)
        self.assertIn("catch (err)", body)
        self.assertIn("setAtlasSubview('overview')", body)

    def test_non_atlas_modes_hide_atlas_panel(self):
        self.assertGreaterEqual(self.ui.count("if (atlasPanelCol) atlasPanelCol.style.display = 'none';"), 3)
        self.assertIn("if (nexusCol) nexusCol.style.display = ''", self.ui)

    def test_restore_is_exception_safe_and_no_auto_fetch(self):
        m = re.search(r"function restoreAtlasSubviewState\(\) \{([\s\S]*?)\n\}", self.ui)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("try {", body)
        self.assertIn("normalizeAtlasSubview", body)
        self.assertIn("setAtlasSubview('overview')", body)
        self.assertNotIn("loadAtlasRunDashboard", body)
        self.assertNotIn("loadPhase8Patches", body)
        self.assertNotIn("loadRecentAtlasRuns", body)

    def test_mobile_atlas_path_restores_and_shows_panel(self):
        m = re.search(r"else if \(name === 'atlas'\) \{([\s\S]*?)\n  \} else if \(name === 'nexus'\)", self.ui)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("setMode('atlas')", body)
        self.assertIn("restoreAtlasSubviewState()", body)
        self.assertIn("atc?.classList.remove('mob-hidden')", body)

    def test_no_destructive_controls(self):
        lower = self.ui.lower()
        for token in ["bulk apply", "bulk approve", "auto apply", "auto approve"]:
            self.assertNotIn(token, lower)


if __name__ == "__main__":
    unittest.main()
