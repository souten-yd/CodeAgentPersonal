from pathlib import Path
import json


def test_vue_next_scaffold_files_exist():
    required = [
        'web/atlas-next/index.html','web/atlas-next/package.json','web/atlas-next/vite.config.ts','web/atlas-next/tsconfig.json',
        'web/atlas-next/src/main.ts','web/atlas-next/src/api/atlasClient.ts',
        'web/atlas-next/src/components/AtlasNextApp.vue','web/atlas-next/src/components/WorkflowShell.vue',
        'web/atlas-next/src/components/StatusCard.vue','web/atlas-next/src/components/SafetySummary.vue',
        'web/atlas-next/src/components/ArtifactSummary.vue','web/atlas-next/src/components/DiagnosticsNotice.vue',
        'ui.html'
    ]
    for f in required:
        assert Path(f).exists(), f


def test_package_contract_and_classic_non_module():
    pkg = json.loads(Path('web/atlas-next/package.json').read_text())
    assert 'vue' in pkg['dependencies']
    dd = pkg['devDependencies']
    assert 'vite' in dd and 'typescript' in dd
    text = Path('web/atlas-next/package.json').read_text().lower()
    assert 'nuxt' not in text and 'next.js' not in text and '"next"' not in text
    for f in ['ui.html', 'web/js/atlas_dashboard.js', 'web/js/atlas_pipeline_api.js']:
        assert 'type="module"' not in Path(f).read_text()
