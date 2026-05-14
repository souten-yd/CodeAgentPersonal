from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SMOKE = ROOT / "scripts" / "smoke_ui_modes_playwright.py"


def test_playwright_smoke_references_feature_manifest():
  source = SMOKE.read_text(encoding="utf-8")
  assert "feature_manifest.json" in source
  assert "load_feature_manifest" in source


def test_playwright_smoke_checks_manifest_sections():
  source = SMOKE.read_text(encoding="utf-8")
  for token in ["tabs", "root_panels", "required_controls", "modules", "panel_selector"]:
    assert token in source


def test_playwright_smoke_reports_manifest_mismatch_clearly():
  source = SMOKE.read_text(encoding="utf-8")
  assert "Feature manifest" in source
  assert "selector" in source
