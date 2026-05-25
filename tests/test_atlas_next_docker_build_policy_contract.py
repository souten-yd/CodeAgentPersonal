from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_docker_build_compiles_atlas_next_after_copy():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    copy_marker = "# Copy full application source at runtime tail to avoid invalidating SBV2/HF/GGUF heavy layers.\nCOPY . /app"
    build_markers = [
        "if [ -f /app/web/atlas-next/package.json ]; then",
        "cd /app/web/atlas-next;",
        "npm ci;",
        "npm run build;",
    ]

    assert copy_marker in dockerfile
    copy_index = dockerfile.index(copy_marker)
    for marker in build_markers:
        assert marker in dockerfile
        assert copy_index < dockerfile.index(marker)


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
