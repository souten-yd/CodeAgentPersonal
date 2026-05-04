import unittest
from pathlib import Path


DOCKERFILE = Path("Dockerfile").read_text(encoding="utf-8")
WORKFLOW = Path(".github/workflows/docker-publish.yml").read_text(encoding="utf-8")
DOCKERIGNORE = Path(".dockerignore").read_text(encoding="utf-8")
UI_SYNTAX = Path("scripts/check_ui_inline_script_syntax.py").read_text(encoding="utf-8")
SMOKE = Path("scripts/smoke_ui_modes_playwright.py").read_text(encoding="utf-8")


class TestPhase302bDockerBuildSpeedContract(unittest.TestCase):
    def test_nodejs_present_in_dockerfile(self):
        self.assertIn("ARG NODE_VERSION=20", DOCKERFILE)
        self.assertIn("node --version", DOCKERFILE)


    def test_node_version_check_is_not_in_llama_prebuilt_stage(self):
        llama_start = DOCKERFILE.index("FROM ubuntu:${UBUNTU_VERSION} AS llama_prebuilt")
        py_base_start = DOCKERFILE.index("FROM nvidia/cuda:${CUDA_VERSION}-devel-ubuntu${UBUNTU_VERSION} AS py_base")
        llama_block = DOCKERFILE[llama_start:py_base_start]
        self.assertNotIn("RUN node --version", llama_block)
        self.assertNotIn("ARG NODE_VERSION=20", llama_block)

    def test_node_version_check_runs_in_py_base_stage(self):
        py_base_start = DOCKERFILE.index("FROM nvidia/cuda:${CUDA_VERSION}-devel-ubuntu${UBUNTU_VERSION} AS py_base")
        py_build_start = DOCKERFILE.index("FROM py_base AS py_build")
        py_base_block = DOCKERFILE[py_base_start:py_build_start]
        self.assertIn("ARG NODE_VERSION=20", py_base_block)
        self.assertIn("node --version", py_base_block)

    def test_inline_syntax_checks_remain_enabled(self):
        self.assertIn("node --check", UI_SYNTAX)
        self.assertIn("check_ui_syntax_main()", SMOKE)

    def test_default_cache_strategy_uses_registry_inline(self):
        self.assertIn("cache-from: type=registry,ref=${{ env.IMAGE_NAME }}:latest", WORKFLOW)
        self.assertIn("cache-to: type=inline", WORKFLOW)
        self.assertNotIn("cache-to: type=gha", WORKFLOW)
        self.assertNotIn("type=gha,mode=max", WORKFLOW)
        self.assertNotIn("type=gha,mode=min", WORKFLOW)

    def test_copy_order_prefers_dependency_layers(self):
        req_copy = DOCKERFILE.index("COPY requirements.txt requirements-tts.txt /app/")
        req_install = DOCKERFILE.index("-r /app/requirements.txt")
        full_copy = DOCKERFILE.rindex("COPY . /app")
        playwright_install = DOCKERFILE.index("playwright install --with-deps chromium")
        self.assertLess(req_copy, req_install)
        self.assertGreater(full_copy, req_install)
        self.assertGreater(full_copy, playwright_install)

    def test_runtime_constraints_unchanged(self):
        self.assertIn("FROM nvidia/cuda:", DOCKERFILE)
        self.assertIn("conda create -n torch_env python=3.11", DOCKERFILE)
        self.assertIn("torch==2.11.0+cu128", DOCKERFILE)
        self.assertIn("torchaudio==2.11.0+cu128", DOCKERFILE)
        self.assertNotIn("pytorch/pytorch", DOCKERFILE)
        self.assertNotIn("deadsnakes", DOCKERFILE)
        self.assertNotIn("keyserver.ubuntu.com", DOCKERFILE)

    def test_debug_harness_safety_strings_not_added(self):
        matrix = Path("scripts/run_debug_test_matrix.py").read_text(encoding="utf-8")
        self.assertNotIn("shell=True", matrix)
        self.assertNotIn("approve_plan", matrix)
        self.assertNotIn("execute_preview", matrix)
        self.assertNotIn("apply_patch", matrix)

    def test_dockerignore_keeps_workflow_available(self):
        self.assertIn(".github", DOCKERIGNORE)
        self.assertIn("!.github/workflows/playwright-ui-smoke.yml", DOCKERIGNORE)


if __name__ == "__main__":
    unittest.main()
