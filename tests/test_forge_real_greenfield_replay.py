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
from pathlib import Path

import pytest

from agent.model_forge import ProfileStore
from agent.model_forge.preset_runner import LocalForgePresetRunner, PresetRunnerTask, write_evidence
from agent.model_forge.route_matrix import ChangeClass
from agent.model_forge.stage_taxonomy import ForgeStage
from app.atlas.capsule.builder import CapsuleBuilder
from app.atlas.capsule.contracts import CapsuleBuildRequest
from app.atlas.capsule.forge_meta import (
    read_capsule_forge_meta,
    record_capsule_replay_via_play_runtime,
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
MODEL_ID = os.environ.get("FORGE_LOCAL_MODEL", "").strip()

_SYSTEM = "You are a web developer. Output only raw HTML, no explanation, no code fences."
_USER = (
    "Create a complete single-file HTML greenfield landing page with an <h1> title "
    "'Forge Greenfield' and a short paragraph. Output only the HTML."
)


def _extract_html(text: str) -> str:
    fenced = re.search(r"```(?:html)?\s*(.*?)```", text, re.DOTALL)
    html = (fenced.group(1) if fenced else text).strip()
    return html


@pytest.mark.real_model
def test_real_greenfield_capsule_replay_updates_profile(tmp_path):
    runner = LocalForgePresetRunner(base_url=BASE_URL, model_id=MODEL_ID, timeout_seconds=180.0)
    if not runner.probe():
        pytest.skip(f"no local model server reachable at {BASE_URL}: {runner.unavailable_reason}")

    run = runner.run(PresetRunnerTask(
        preset_id="greenfield_standard",
        stage=ForgeStage.PLANNING,
        change_class=ChangeClass.GREENFIELD,
        task_category="greenfield",
        system_prompt=_SYSTEM,
        user_prompt=_USER,
        output_contract="text",
        requirement_coverage_ratio=1.0,
    ))
    assert run.execution_result.contract_valid is True, run.execution_result.errors
    html = _extract_html(run.raw_output)
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
        "provider_id": run.provider_id, "model_id": run.model_id,
        "route_id": "greenfield_skeleton", "stage": "planning", "dimension": "greenfield",
    })
    meta = read_capsule_forge_meta(tmp_path, "forge.greenfield", "1.0.0", content_hash)
    assert meta is not None and meta.model_id == run.model_id  # runnable Capsule WITH a Forge trace

    # Replay the Capsule through the Play runtime: record a measured run into the model profile.
    store = ProfileStore(tmp_path / "profiles")
    evidence = record_capsule_replay_via_play_runtime(
        tmp_path, store, package_id="forge.greenfield", version="1.0.0",
        content_hash=content_hash,
    )
    assert evidence.package_immutable_verified is True
    assert evidence.profile_updated is True
    assert evidence.runtime_status == "passed"
    assert evidence.runtime_evidence_ref.startswith("play_session:")
    profile = store.load_profile(run.provider_id, run.model_id)
    assert profile.dimension_scores["greenfield"] == 1.0

    out = run.evidence_payload(package="PFG-33")
    out.update(
        content_hash=content_hash,
        capsule_built=built["status"],
        forge_trace_attached=True,
        replay_immutable_verified=evidence.package_immutable_verified,
        runtime_verdict="passed" if evidence.profile_updated else "failed",
        runtime_status=evidence.runtime_status,
        runtime_evidence_ref=evidence.runtime_evidence_ref,
        preview_status=evidence.preview_status,
        greenfield_score=profile.dimension_scores["greenfield"],
        html_excerpt=html[:200],
        legacy_direct_http_orchestration=False,
    )
    out_dir = Path(os.environ.get("CODEAGENT_CA_DATA_DIR", "ca_data")) / "model_forge" / "evidence"
    write_evidence(out_dir / "pfg33_greenfield_replay.json", out)
    print("PFG-33 evidence:", json.dumps(out, ensure_ascii=False))
