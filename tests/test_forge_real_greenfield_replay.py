"""PFG-33 — real Greenfield Capsule replay run.

Completes the Portal x Forge loop with real model evidence: the local model generates a
Greenfield single-file web app, a real Capsule is built from it, a Forge trace is attached
to the Capsule, and a replay records the run outcome into the model profile while verifying
the package ZIP is immutable. The result is at least one runnable Capsule with a Forge
trace whose replay updated the model profile.

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

from agent.model_forge import ProfileStore
from app.atlas.capsule.builder import CapsuleBuilder
from app.atlas.capsule.contracts import CapsuleBuildRequest
from app.atlas.capsule.forge_meta import (
    read_capsule_forge_meta,
    record_capsule_replay,
    write_capsule_forge_meta,
)
from app.atlas.play.contracts import LaunchKind, LaunchProfile
from app.atlas.play.environment import build_structured_launch_adapter
from app.atlas.play.sessions import (
    PlayProcessPolicy,
    PlaySessionRecord,
    PlaySessionRepository,
)

BASE_URL = os.environ.get("FORGE_LOCAL_BASE_URL", "http://localhost:8080").rstrip("/")

_SYSTEM = "You are a web developer. Output only raw HTML, no explanation, no code fences."
_USER = (
    "Create a complete single-file HTML greenfield landing page with an <h1> title "
    "'Forge Greenfield' and a short paragraph. Output only the HTML."
)


def _server_model() -> str | None:
    try:
        with urllib.request.urlopen(BASE_URL + "/v1/models", timeout=3) as resp:  # noqa: S310
            data = json.loads(resp.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, OSError, ValueError):
        return None
    models = data.get("data") or data.get("models") or []
    return str((models[0].get("id") or models[0].get("name")) if models else "")


def _chat(model: str | None) -> str | None:
    payload = {
        "messages": [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": _USER}],
        "stream": False, "temperature": 0,
    }
    if model:
        payload["model"] = model
    req = urllib.request.Request(
        BASE_URL + "/v1/chat/completions", method="POST",
        data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:  # noqa: S310
            return json.loads(resp.read().decode("utf-8", "replace"))["choices"][0]["message"]["content"]
    except (urllib.error.URLError, OSError, ValueError, KeyError):
        return None


def _extract_html(text: str) -> str:
    fenced = re.search(r"```(?:html)?\s*(.*?)```", text, re.DOTALL)
    html = (fenced.group(1) if fenced else text).strip()
    return html


@pytest.mark.real_model
def test_real_greenfield_capsule_replay_updates_profile(tmp_path):
    model = _server_model()
    if model is None:
        pytest.skip(f"no local model server reachable at {BASE_URL}")

    raw = _chat(model)
    assert raw, "no model response"
    html = _extract_html(raw)
    assert "<" in html and "html" in html.lower()

    work = tmp_path / "atlas" / "projects" / "demo" / "work"
    work.mkdir(parents=True)
    (work / "index.html").write_text(html, encoding="utf-8")

    profiles = [LaunchProfile(profile_id="web", name="Web", kind=LaunchKind.STATIC_WEB, entrypoint="index.html")]
    adapter = build_structured_launch_adapter(work, profiles[0])
    PlaySessionRepository(tmp_path).save(PlaySessionRecord(
        session_id="play-green", project_id="demo", project_root=str(work),
        state="stopped", launch_profile_id="web", launch_kind=adapter.kind,
        adapter=adapter.model_dump(mode="json"),
        process_policy=PlayProcessPolicy(uses_process_group=True, cleanup_strategy="test"),
        exit_code=0,
    ))

    # Build a REAL Capsule from the model-generated greenfield app.
    built = CapsuleBuilder(tmp_path).build(CapsuleBuildRequest(
        project_id="demo", play_session_id="play-green", selected_profile_ids=["web"],
        package_id="forge.greenfield", name="Forge Greenfield", version="1.0.0",
        launch_profiles=profiles, default_profile_id="web",
    ))
    record = built["record"]
    content_hash = record["content_hash"]
    assert built["status"] == "built"
    assert record["storage_path"].endswith(f"{content_hash}.zip")

    # Attach a Forge trace to the Capsule (sidecar; ZIP untouched).
    write_capsule_forge_meta(tmp_path, {
        "package_id": "forge.greenfield", "version": "1.0.0", "content_hash": content_hash,
        "provider_id": "local_openai_compatible", "model_id": model,
        "route_id": "greenfield_skeleton", "stage": "planning", "dimension": "greenfield",
    })
    meta = read_capsule_forge_meta(tmp_path, "forge.greenfield", "1.0.0", content_hash)
    assert meta is not None and meta.model_id == model  # runnable Capsule WITH a Forge trace

    # Replay the Capsule: record a successful run into the model profile.
    store = ProfileStore(tmp_path / "profiles")
    evidence = record_capsule_replay(
        tmp_path, store, package_id="forge.greenfield", version="1.0.0",
        content_hash=content_hash, runtime_passed=True,
    )
    assert evidence.package_immutable_verified is True
    assert evidence.profile_updated is True
    profile = store.load_profile("local_openai_compatible", model)
    assert profile.dimension_scores["greenfield"] == 1.0

    out = {
        "package": "PFG-33", "model_id": model, "content_hash": content_hash,
        "capsule_built": built["status"], "forge_trace_attached": True,
        "replay_immutable_verified": evidence.package_immutable_verified,
        "greenfield_score": profile.dimension_scores["greenfield"],
        "html_excerpt": html[:200],
    }
    out_dir = Path(os.environ.get("CODEAGENT_CA_DATA_DIR", "ca_data")) / "model_forge" / "evidence"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "pfg33_greenfield_replay.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("PFG-33 evidence:", json.dumps(out, ensure_ascii=False))
