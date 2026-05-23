from pathlib import Path
VUE=Path('web/atlas-next/src/components/Level1ReadinessPanel.vue').read_text()
MANIFEST=Path('web/atlas_ui_surface_manifest.json').read_text()

def test_no_dynamic_execution_primitives():
    for token in ['eval(', 'new Function', 'Function(']:
        assert token not in VUE

def test_manifest_retains_disabled_execution_flags():
    for token in ['"runtime_level": "level_0_manual_only"','"level1_execution_enabled": false','"autonomous_execution_enabled": false']:
        assert token in MANIFEST
