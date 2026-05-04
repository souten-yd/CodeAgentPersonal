import unittest
from pathlib import Path

DOCKERFILE = Path("Dockerfile").read_text(encoding="utf-8")
UI_SYNTAX = Path("scripts/check_ui_inline_script_syntax.py").read_text(encoding="utf-8")
SMOKE = Path("scripts/smoke_ui_modes_playwright.py").read_text(encoding="utf-8")
WORKFLOW = Path(".github/workflows/docker-publish.yml").read_text(encoding="utf-8")
MATRIX = Path("scripts/run_debug_test_matrix.py").read_text(encoding="utf-8")


class TestPhase302eModernNodeRuntimeContract(unittest.TestCase):
    def test_dockerfile_installs_modern_node(self):
        self.assertIn("ARG NODE_VERSION=20", DOCKERFILE)
        self.assertIn("https://nodejs.org/dist/v${NODE_VERSION}", DOCKERFILE)
        self.assertIn("node --version", DOCKERFILE)
        self.assertIn('node -e "const x={a:{b:1}}; console.log(x.a?.b)"', DOCKERFILE)

    def test_old_apt_nodejs_is_not_the_only_implementation(self):
        self.assertNotIn("apt-get install -y --no-install-recommends --fix-missing \\\n        nodejs", DOCKERFILE)
        self.assertIn("/usr/local/bin/node", DOCKERFILE)

    def test_ui_syntax_checker_validates_node_version(self):
        self.assertIn("NODE_BINARY", UI_SYNTAX)
        self.assertIn("--version", UI_SYNTAX)
        self.assertIn("major < 18", UI_SYNTAX)
        self.assertIn("Node.js >=18 is required for inline UI syntax checks.", UI_SYNTAX)

    def test_syntax_check_remains_enabled(self):
        self.assertIn("node --check", UI_SYNTAX)
        self.assertIn("check_ui_syntax_main()", SMOKE)

    def test_cache_optimization_remains(self):
        self.assertNotIn("cache-to: type=gha", WORKFLOW)
        self.assertIn("cache-to: type=inline", WORKFLOW)

    def test_safety_remains(self):
        self.assertNotIn("shell=True", MATRIX)
        self.assertNotIn("approve_plan", MATRIX)
        self.assertNotIn("execute_preview", MATRIX)
        self.assertNotIn("apply_patch", MATRIX)


if __name__ == "__main__":
    unittest.main()
