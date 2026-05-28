from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_docker_build_does_not_compile_atlas_next():
    """POST-SCALE-160-UI-DEFAULT-RECONFIRM: the buildless ui.html shell is
    the only Atlas default, so the optional Vue/atlas-next preview is no
    longer built at image-build time. The forbidden tokens must NOT appear in
    the Dockerfile."""

    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    copy_marker = "# Copy full application source at runtime tail to avoid invalidating SBV2/HF/GGUF heavy layers.\nCOPY . /app"
    assert copy_marker in dockerfile

    forbidden_build_markers = [
        "if [ -f /app/web/atlas-next/package.json ]; then",
        "cd /app/web/atlas-next;",
        "npm ci;",
        "npm run build;",
    ]
    for marker in forbidden_build_markers:
        assert marker not in dockerfile, f"Dockerfile must not contain '{marker}' after UI default reconfirmation"


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
