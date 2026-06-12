"""PFG-31 — real Web App / Portal run preset.

End-to-end real evidence: the local model GENERATES a single-file web app, the artifact is
RUN through the real Portal/Play static-web runtime (the same runtime Portal Run uses), the
served preview is verified, and the Portal runtime outcome is fed into the model profile.
The candidate is never auto-applied (no Safe Apply bypass).

Skips when no local model server is reachable (FORGE_LOCAL_BASE_URL, default :8080).
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent.model_forge import PortalRunEvidence, ProfileStore, ingest_portal_evidence
from app.api.atlas_play import router as atlas_play_router
from app.atlas.play.contracts import LaunchKind, LaunchProfile
from app.atlas.play.environment import build_structured_launch_adapter
from app.atlas.play.sessions import PlaySessionManager

BASE_URL = os.environ.get("FORGE_LOCAL_BASE_URL", "http://localhost:8080").rstrip("/")

_SYSTEM = "You are a web developer. Output only raw HTML, no explanation, no code fences."
_USER = (
    "Create a complete single-file HTML document for a page with an <h1> that says "
    "'Hello Forge' and a button labelled 'Greet' that shows an alert. Output only the HTML."
)


def _chat(model: str | None) -> str | None:
    payload = {
        "messages": [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": _USER}],
        "stream": False, "temperature": 0,
    }
    if model:
        payload["model"] = model
    req = urllib.request.Request(
        BASE_URL + "/v1/chat/completions", method="POST",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:  # noqa: S310
            body = json.loads(resp.read().decode("utf-8", "replace"))
        return body["choices"][0]["message"]["content"]
    except (urllib.error.URLError, OSError, ValueError, KeyError):
        return None


def _server_model() -> str | None:
    try:
        with urllib.request.urlopen(BASE_URL + "/v1/models", timeout=3) as resp:  # noqa: S310
            data = json.loads(resp.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, OSError, ValueError):
        return None
    models = data.get("data") or data.get("models") or []
    return str((models[0].get("id") or models[0].get("name")) if models else "")


def _extract_html(text: str) -> str:
    # Strip code fences if the model added them despite instructions.
    fenced = re.search(r"```(?:html)?\s*(.*?)```", text, re.DOTALL)
    html = fenced.group(1) if fenced else text
    return html.strip()


@pytest.mark.real_model
def test_real_webapp_reaches_portal_runtime_and_updates_profile(tmp_path):
    model = _server_model()
    if model is None:
        pytest.skip(f"no local model server reachable at {BASE_URL}")

    raw = _chat(model)
    assert raw, "no model response"
    html = _extract_html(raw)
    assert "<" in html and "html" in html.lower(), f"model did not produce HTML: {html[:200]}"

    # Write the model-generated artifact into a project work dir.
    work = tmp_path / "atlas" / "projects" / "forge_web" / "work"
    work.mkdir(parents=True)
    (work / "index.html").write_text(html, encoding="utf-8")

    # RUN it through the real Portal/Play static-web runtime.
    app = FastAPI()
    app.state.atlas_ca_data_root = str(tmp_path)
    app.include_router(atlas_play_router)
    client = TestClient(app)
    manager = PlaySessionManager(tmp_path)
    adapter = build_structured_launch_adapter(
        work, LaunchProfile(profile_id="web", name="Web", kind=LaunchKind.STATIC_WEB, entrypoint="index.html"),
    )
    session = manager.start_session(project_id="forge_web", project_root=work, adapter=adapter)
    try:
        preview = client.get(f"/api/atlas/play/preview/{session.session_id}/index.html")
        runtime_passed = preview.status_code == 200 and bool(preview.content)
        # Real preview evidence: the runtime serves the model's artifact (compare with
        # newlines normalised — the static server may emit CRLF).
        if runtime_passed:
            served = preview.content.decode("utf-8", "replace").replace("\r\n", "\n").strip()
            assert served == html.replace("\r\n", "\n").strip()
    finally:
        stopped = manager.stop_session(session.session_id)

    # Feed the Portal runtime outcome into the model profile (Portal evidence is strong).
    store = ProfileStore(tmp_path / "profiles")
    result = ingest_portal_evidence(store, PortalRunEvidence(
        installation_id="forge_web", provider_id="local_openai_compatible", model_id=model,
        dimension="web_app", runtime_passed=runtime_passed,
        evidence_refs=[f"play_session:{session.session_id}"],
    ))
    assert runtime_passed is True, "Portal static preview did not serve the artifact"
    assert result.strength == "strong_runtime" and result.moved_score is True
    profile = store.load_profile("local_openai_compatible", model)
    assert profile.dimension_scores["web_app"] == 1.0

    evidence = {
        "package": "PFG-31", "model_id": model, "html_bytes": len(html),
        "preview_status": preview.status_code, "runtime_passed": runtime_passed,
        "web_app_score": profile.dimension_scores["web_app"],
        "html_excerpt": html[:300],
    }
    out_dir = Path(os.environ.get("CODEAGENT_CA_DATA_DIR", "ca_data")) / "model_forge" / "evidence"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "pfg31_webapp_portal.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print("PFG-31 evidence:", json.dumps(evidence, ensure_ascii=False))
