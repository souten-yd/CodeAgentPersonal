from agent.model_forge.method_artifacts import InMemoryMethodArtifactStore
from agent.model_forge.method_contracts import MethodRequest
from agent.model_forge.method_taxonomy import MethodVariant
from agent.model_forge.route_taxonomy import ForgeRoute
from agent.model_forge.twin_edit_slots import TwinEditSlot, TwinEditSlotResolver
from agent.model_forge.twin_slot_adapter import TwinLocalizedSlotPatchAdapter


def test_resolver_finds_python_symbol_with_unique_atlas_owned_anchor(tmp_path):
    (tmp_path / "mod.py").write_text("def keep():\n    return 1\n\ndef render(value):\n    return value\n", encoding="utf-8")
    slot = TwinEditSlotResolver().resolve(project_root=tmp_path, target_file="mod.py", goal="change render", expected_symbols=["render"])
    assert slot.symbol_ref == "render"
    assert slot.operation == "replace_symbol_body"
    assert slot.anchor_text == "def render(value):"
    assert slot.anchor_occurrences == 1


def test_resolver_uses_only_explicit_unique_insertion_boundary(tmp_path):
    (tmp_path / "large.py").write_text("x = 1\n# UNIQUE_UTILITY_BOUNDARY\ny = 2\n", encoding="utf-8")
    slot = TwinEditSlotResolver().resolve(project_root=tmp_path, target_file="large.py", goal="add helper", expected_symbols=["missing"])
    assert slot.operation == "insert_after"
    assert slot.anchor_text == "# UNIQUE_UTILITY_BOUNDARY"
    (tmp_path / "large.py").write_text("# UNIQUE_A\n# UNIQUE_B\n", encoding="utf-8")
    assert TwinEditSlotResolver().resolve(project_root=tmp_path, target_file="large.py", goal="add", expected_symbols=["missing"]) is None


def _request(slot):
    return MethodRequest(request_id="r1", route=ForgeRoute.PATCH_DSL, method_variant=MethodVariant.TWIN_LOCALIZED_SLOT_PATCH, model_id="m", provider_id="p", goal="fill slot", metadata={"twin_edit_slot": slot.model_dump()})


def test_slot_adapter_compiles_fill_without_model_owned_anchor_or_apply():
    store = InMemoryMethodArtifactStore()
    adapter = TwinLocalizedSlotPatchAdapter(store)
    slot = TwinEditSlot(slot_id="s", file="mod.py", operation="insert_after", start_line=1, end_line=1, anchor_text="# UNIQUE", anchor_occurrences=1, confidence=0.9)
    request = _request(slot)
    prompt = adapter.prepare_prompt(request)
    assert "Do not choose or repeat an anchor" in prompt.system_text
    result = adapter.verify_contract(request, adapter.compile_patch(request, adapter.parse_output(request, "def added():\n    return 2")))
    assert result.status == "passed"
    assert result.contract_valid is True
    assert result.safe_apply_ready is False
    patch = store.get(result.patch_ref)
    assert patch["approval_required"] is True
    assert patch["file_changes"][0]["edits"][0]["old_string"] == "# UNIQUE"


def test_slot_adapter_blocks_repeated_or_ambiguous_anchor():
    adapter = TwinLocalizedSlotPatchAdapter()
    unique = TwinEditSlot(slot_id="s", file="mod.py", operation="insert_after", anchor_text="# UNIQUE", anchor_occurrences=1)
    assert adapter.parse_output(_request(unique), "# UNIQUE\ndef bad(): pass").status == "blocked"
    ambiguous = unique.model_copy(update={"anchor_occurrences": 2})
    parsed = adapter.parse_output(_request(ambiguous), "def added(): pass")
    assert adapter.compile_patch(_request(ambiguous), parsed).blocked_reasons == ["slot_anchor_not_unique"]
