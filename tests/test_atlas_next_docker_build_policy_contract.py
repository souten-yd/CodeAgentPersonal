from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_docker_build_compiles_atlas_next_after_copy():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    copy_marker = "# Copy full application source at runtime tail to avoid invalidating SBV2/HF/GGUF heavy layers.\nCOPY . /app"
    build_block = "cd /app/web/atlas-next; \\\n      npm ci; \\\n      npm run build"

    assert copy_marker in dockerfile
    assert build_block in dockerfile
    assert dockerfile.index(copy_marker) < dockerfile.index(build_block)


def test_policy_keeps_vue_build_out_of_runtime_startup():
    policy = (ROOT / "docs" / "atlas_next_child_view_build_policy.md").read_text(encoding="utf-8")
    startup = (ROOT / "scripts" / "start_codeagent.py").read_text(encoding="utf-8")

    assert "Runtime/server startup must not run `npm install`, `npm ci`, or `npm run build`" in policy
    forbidden = [
        "ensure_atlas_next_dist",
        "CODEAGENT_ATLAS_NEXT_BUILD",
        "npm run build",
        "npm ci",
    ]
    for token in forbidden:
        assert token not in startup
