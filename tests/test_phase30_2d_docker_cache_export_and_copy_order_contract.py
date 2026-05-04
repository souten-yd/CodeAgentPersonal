import unittest
from pathlib import Path


DOCKERFILE = Path("Dockerfile").read_text(encoding="utf-8")
WORKFLOW = Path(".github/workflows/docker-publish.yml").read_text(encoding="utf-8")
MATRIX = Path("scripts/run_debug_test_matrix.py").read_text(encoding="utf-8")


class TestPhase302dDockerCacheExportAndCopyOrderContract(unittest.TestCase):
    def test_workflow_disables_gha_cache_export_by_default(self):
        self.assertNotIn("cache-to: type=gha", WORKFLOW)
        self.assertNotIn("type=gha,mode=max", WORKFLOW)
        self.assertNotIn("type=gha,mode=min", WORKFLOW)

    def test_workflow_uses_registry_inline_cache(self):
        self.assertIn("cache-from: type=registry,ref=${{ env.IMAGE_NAME }}:latest", WORKFLOW)
        self.assertIn("cache-to: type=inline", WORKFLOW)

    def test_full_copy_moves_after_style_bert_vits2_stage(self):
        req_copy = DOCKERFILE.index("COPY requirements.txt requirements-tts.txt /app/")
        req_install = DOCKERFILE.index("-r /app/requirements.txt")
        stage_boundary = DOCKERFILE.index("FROM py_build AS style_bert_vits2_build")
        runtime_stage = DOCKERFILE.index("FROM style_bert_vits2_build AS runtime")
        full_copy = DOCKERFILE.rindex("COPY . /app")
        gguf_download = DOCKERFILE.index("repo_id=\"unsloth/gemma-4-E4B-it-GGUF\"")

        self.assertLess(req_copy, req_install)
        self.assertLess(stage_boundary, full_copy)
        self.assertLess(runtime_stage, full_copy)
        self.assertLess(gguf_download, full_copy)

        py_build_block = DOCKERFILE[DOCKERFILE.index("FROM py_base AS py_build"):stage_boundary]
        self.assertNotIn("COPY . /app", py_build_block)

    def test_node_playwright_and_runtime_constraints_preserved(self):
        self.assertIn("ARG NODE_VERSION=20", DOCKERFILE)
        self.assertIn("node --version", DOCKERFILE)
        self.assertIn("playwright", DOCKERFILE)
        self.assertIn("playwright install --with-deps chromium", DOCKERFILE)
        self.assertIn("FROM nvidia/cuda:", DOCKERFILE)
        self.assertIn("conda create -n torch_env python=3.11", DOCKERFILE)
        self.assertIn("torch==2.11.0+cu128", DOCKERFILE)
        self.assertIn("torchaudio==2.11.0+cu128", DOCKERFILE)
        self.assertNotIn("pytorch/pytorch", DOCKERFILE)
        self.assertNotIn("deadsnakes", DOCKERFILE)
        self.assertNotIn("keyserver.ubuntu.com", DOCKERFILE)

    def test_debug_harness_safety_preserved(self):
        self.assertNotIn("shell=True", MATRIX)
        self.assertNotIn("approve_plan", MATRIX)
        self.assertNotIn("execute_preview", MATRIX)
        self.assertNotIn("apply_patch", MATRIX)


if __name__ == "__main__":
    unittest.main()
