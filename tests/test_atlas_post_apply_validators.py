from agent.atlas_post_apply_validators import (
    api_route_reference_validator,
    config_env_key_validator,
    import_export_validator,
    json_shape_validator,
    resource_contract_validator,
    run_post_apply_validators,
    slice_marker_validator,
)


def _codes(result: dict) -> set[str]:
    return {str(v.get("code") or "") for v in result.get("violations") or []}


def test_import_export_validator_reports_missing_named_export():
    out = import_export_validator({
        "src/App.tsx": "import { MissingWidget } from './widgets';\nexport function App(){ return MissingWidget(); }\n",
        "src/widgets.ts": "export function PresentWidget(){ return null; }\n",
    })

    assert "import_export_missing_export" in _codes(out)
    violation = out["violations"][0]
    assert violation["contract_type"] == "interface"
    assert violation["evidence"]["resolved_path"] == "src/widgets.ts"
    assert violation["evidence"]["imported_name"] == "MissingWidget"


def test_api_route_reference_validator_reports_missing_handler():
    out = api_route_reference_validator({
        "server.py": '@app.get("/api/users")\ndef users(): pass\n',
        "web/client.ts": "export async function load(){ return fetch('/api/accounts') }\n",
    })

    assert "api_route_missing_handler" in _codes(out)


def test_config_env_key_validator_reports_business_config_mismatch():
    out = config_env_key_validator({
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


def test_json_shape_validator_reports_invalid_json():
    out = json_shape_validator({"config/settings.json": '{"feature": true,,}\n'})

    assert "json_invalid" in _codes(out)
    assert out["violations"][0]["evidence"]["line"] == 1


def test_resource_validator_represents_webgl_as_resource_violation():
    out = resource_contract_validator({
        "index.html": '<canvas id="gameCanvas"></canvas><script src="https://cdn.example/three.min.js"></script>',
        "main.js": (
            "const renderer = new THREE.WebGLRenderer({ canvas: document.getElementById('gameCanvas') });\n"
            "const canvas = document.getElementById('gameCanvas');\n"
            "const ctx = canvas.getContext('2d');\n"
        ),
    })

    assert "webgl_canvas_2d_context_conflict" in _codes(out)
    assert out["violations"][0]["contract_type"] == "resource"


def test_slice_marker_validator_blocks_post_apply_slice_text():
    out = slice_marker_validator({"src/app.ts": "const a = 1;\n... omitted\nconst z = 2;\n"})

    assert out["violations"] == [{
        "code": "slice_marker_present",
        "contract_type": "resource",
        "path": "src/app.ts",
        "severity": "error",
        "evidence": {"marker": "... omitted"},
    }]


def test_run_post_apply_validators_aggregates_structured_results():
    out = run_post_apply_validators(
        {
            "src/App.tsx": "import { MissingWidget } from './widgets';\n",
            "src/widgets.ts": "export function PresentWidget(){ return null; }\n",
            ".env.example": "PUBLIC_API_URL=https://example.test\n",
            "src/config.ts": "export const url = process.env.PRIVATE_API_URL;\n",
        },
        preview_result={
            "file_results": [{
                "path": "src/App.tsx",
                "content_mode": "full_content",
                "target_existed": True,
            }],
        },
    )

    codes = _codes(out)
    assert {"import_export_missing_export", "env_key_mismatch", "forbidden_full_content"} <= codes
    assert any(v["name"] == "import_export_validator" and v["status"] == "failed" for v in out["validators"])
    assert all("name" in v and "violation_count" in v for v in out["validators"])
