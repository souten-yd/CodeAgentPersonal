from pathlib import Path

import pytest

from agent.atlas_plan_pool_schema import AtlasPlanItem
from agent.atlas_post_apply_preview import preview_plan_item_post_apply


def _item(*, target_files=None, metadata=None):
    return AtlasPlanItem(
        item_id="i1",
        pool_id="p1",
        title="t",
        goal="g",
        item_type="implementation",
        risk_level="low",
        status="ready",
        target_files=target_files or ["app.js"],
        metadata={"action_type": "update", **(metadata or {})},
    )


def test_preview_exact_edit_returns_full_post_apply_js_content_without_writing(tmp_path):
    target = Path(tmp_path) / "src/app.ts"
    target.parent.mkdir()
    original = "\n".join([
        "export function total(items: number[]) {",
        "  return items.reduce((sum, item) => sum + item, 0);",
        "}",
        "",
    ])
    target.write_text(original, encoding="utf-8")
    item = _item(
        target_files=["src/app.ts"],
        metadata={
            "edits": [{
                "old_string": "return items.reduce((sum, item) => sum + item, 0);",
                "new_string": "return items.reduce((sum, item) => sum + item, 10);",
            }],
        },
    )

    out = preview_plan_item_post_apply(item=item, workspace_root=tmp_path)

    assert out["applied"] is True
    assert out["blocked_changes"] == []
    assert out["post_apply_content_by_path"]["src/app.ts"].startswith("export function total")
    assert "sum + item, 10" in out["post_apply_content_by_path"]["src/app.ts"]
    assert target.read_text(encoding="utf-8") == original


@pytest.mark.parametrize(
    ("path", "original", "old", "new"),
    [
        ("service.py", "def enabled():\n    return False\n", "return False", "return True"),
        ("config.json", '{\n  "enabled": false\n}\n', '"enabled": false', '"enabled": true'),
        ("form.yaml", "fields:\n  email: required\n", "email: required", "email: optional"),
        ("notes.txt", "status=old\n", "status=old", "status=new"),
    ],
)
def test_preview_edits_common_file_types(path, original, old, new, tmp_path):
    target = Path(tmp_path) / path
    target.write_text(original, encoding="utf-8")
    item = _item(
        target_files=[path],
        metadata={"edits": [{"old_string": old, "new_string": new}]},
    )

    out = preview_plan_item_post_apply(item=item, workspace_root=tmp_path)

    assert out["applied"] is True
    assert new in out["post_apply_content_by_path"][path]
    assert target.read_text(encoding="utf-8") == original


def test_preview_multiple_files_keeps_unrelated_target_unchanged(tmp_path):
    (Path(tmp_path) / "a.txt").write_text("alpha\n", encoding="utf-8")
    (Path(tmp_path) / "b.txt").write_text("beta\n", encoding="utf-8")
    item = _item(
        target_files=["a.txt", "b.txt"],
        metadata={
            "file_changes": [
                {
                    "path": "a.txt",
                    "action_type": "update",
                    "content_mode": "edits",
                    "edits": [{"old_string": "alpha", "new_string": "ALPHA"}],
                }
            ],
        },
    )

    out = preview_plan_item_post_apply(item=item, workspace_root=tmp_path)

    assert out["applied"] is True
    assert out["post_apply_content_by_path"]["a.txt"] == "ALPHA\n"
    assert out["post_apply_content_by_path"]["b.txt"] == "beta\n"
    assert (Path(tmp_path) / "a.txt").read_text(encoding="utf-8") == "alpha\n"
    assert (Path(tmp_path) / "b.txt").read_text(encoding="utf-8") == "beta\n"


def test_preview_blocks_slice_derived_full_content(tmp_path):
    target = Path(tmp_path) / "large.js"
    target.write_text("const a = 1;\nconst b = 2;\n", encoding="utf-8")
    item = _item(
        target_files=["large.js"],
        metadata={
            "content_mode": "full_content",
            "current_file_content_sliced": True,
            "proposed_content": "const a = 1;\n// ... (20 unrelated line(s) omitted -- full file is on disk) ...\n",
        },
    )

    out = preview_plan_item_post_apply(item=item, workspace_root=tmp_path)

    assert out["applied"] is False
    assert out["reasons"] == ["slice_full_content_forbidden"]
    assert out["blocked_changes"][0]["path"] == "large.js"
    assert out["post_apply_content_by_path"]["large.js"] == "const a = 1;\nconst b = 2;\n"


def test_preview_blocks_slice_marker_even_without_sliced_flag(tmp_path):
    target = Path(tmp_path) / "large.js"
    target.write_text("const a = 1;\nconst b = 2;\n", encoding="utf-8")
    item = _item(
        target_files=["large.js"],
        metadata={
            "content_mode": "full_content",
            "proposed_content": "const a = 1;\n// rest of the file unchanged\n",
        },
    )

    out = preview_plan_item_post_apply(item=item, workspace_root=tmp_path)

    assert out["applied"] is False
    assert out["reasons"] == ["slice_marker_forbidden_in_full_content"]


def test_preview_create_full_content_for_new_file(tmp_path):
    item = _item(
        target_files=["new.json"],
        metadata={
            "action_type": "create",
            "proposed_content": '{"ok": true}\n',
        },
    )

    out = preview_plan_item_post_apply(item=item, workspace_root=tmp_path)

    assert out["applied"] is True
    assert out["post_apply_content_by_path"]["new.json"] == '{"ok": true}\n'
    assert not (Path(tmp_path) / "new.json").exists()


def test_preview_can_require_policy_for_existing_full_content(tmp_path):
    target = Path(tmp_path) / "doc.txt"
    target.write_text("old\n", encoding="utf-8")
    item = _item(
        target_files=["doc.txt"],
        metadata={"proposed_content": "new\n"},
    )

    out = preview_plan_item_post_apply(
        item=item,
        workspace_root=tmp_path,
        allow_existing_full_content=False,
    )

    assert out["applied"] is False
    assert out["reasons"] == ["full_content_requires_policy"]
    assert target.read_text(encoding="utf-8") == "old\n"

