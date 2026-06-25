from pathlib import Path

from agent.atlas_contract_registry import evaluate_project_contracts
from agent.atlas_plan_pool_schema import AtlasPlanItem
from agent.atlas_post_apply_preview import preview_plan_item_post_apply


def _preview(tmp_path, *, path: str, original: str, old: str, new: str) -> dict:
    target = Path(tmp_path) / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(original, encoding="utf-8")
    item = AtlasPlanItem(
        item_id="i1",
        pool_id="p1",
        title="t",
        goal="g",
        item_type="implementation",
        risk_level="low",
        status="ready",
        target_files=[path],
        metadata={
            "action_type": "update",
            "edits": [{"old_string": old, "new_string": new}],
        },
    )
    return preview_plan_item_post_apply(item=item, workspace_root=tmp_path)


def test_api_endpoint_mismatch_uses_post_apply_preview(tmp_path):
    (Path(tmp_path) / "server.py").write_text('@app.get("/api/users")\ndef users(): pass\n', encoding="utf-8")
    original = "export async function load(){ return fetch('/api/users') }\n"
    preview = _preview(
        tmp_path,
        path="web/client.ts",
        original=original,
        old="/api/users",
        new="/api/accounts",
    )

    out = evaluate_project_contracts(preview["post_apply_content_by_path"] | {
        "server.py": (Path(tmp_path) / "server.py").read_text(encoding="utf-8"),
    })

    assert any(v["code"] == "api_route_missing_handler" and v["evidence"]["route"] == "/api/accounts" for v in out["violations"])
    assert any(c["contract_id"] == "interface:api_routes" for c in out["contracts"])


def test_env_key_mismatch_is_reported():
    out = evaluate_project_contracts({
        ".env.example": "PUBLIC_API_URL=https://example.test\n",
        "src/config.ts": "export const url = process.env.PRIVATE_API_URL;\n",
    })

    assert out["violations"] == [{
        "code": "env_key_mismatch",
        "contract_type": "resource",
        "path": "src/config.ts",
        "severity": "error",
        "evidence": {"key": "PRIVATE_API_URL", "defined_keys": ["PUBLIC_API_URL"]},
    }]


def test_json_schema_and_yaml_form_field_mismatch_is_reported():
    out = evaluate_project_contracts({
        "schema/user.schema.json": '{"required":["email","name"],"properties":{"email":{},"name":{}}}',
        "forms/user.yaml": "fields:\n  name:\n    label: Name\n",
    })

    assert any(v["code"] == "form_validation_field_mismatch" and v["evidence"]["field"] == "email" for v in out["violations"])
    assert any(c["contract_id"] == "data:json_schema_fields" for c in out["contracts"])
    assert any(c["contract_id"] == "data:yaml_form_fields" for c in out["contracts"])


def test_webgl_canvas_conflict_is_a_resource_contract_violation():
    out = evaluate_project_contracts({
        "index.html": '<canvas id="gameCanvas"></canvas><script src="https://cdn.example/three.min.js"></script>',
        "main.js": (
            "const renderer = new THREE.WebGLRenderer({ canvas: document.getElementById('gameCanvas') });\n"
            "const canvas = document.getElementById('gameCanvas');\n"
            "const ctx = canvas.getContext('2d');\n"
        ),
    })

    assert any(v["code"] == "webgl_canvas_2d_context_conflict" for v in out["violations"])
    assert any(c["contract_id"] == "resource:shared_app_surface" for c in out["contracts"])


def test_matching_contracts_return_no_violations():
    out = evaluate_project_contracts({
        "server.js": "app.get('/api/users', (req, res) => res.json([]));\n",
        "client.ts": "fetch('/api/users');\n",
        ".env.example": "PUBLIC_API_URL=https://example.test\n",
        "config.ts": "const url = process.env.PUBLIC_API_URL;\n",
        "schema/user.schema.json": '{"required":["email"],"properties":{"email":{}}}',
        "forms/user.yaml": "fields:\n  email:\n    label: Email\n",
    })

    assert out["violations"] == []

