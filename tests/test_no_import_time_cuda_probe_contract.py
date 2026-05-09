import importlib
import json
import subprocess
import sys
import textwrap
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_probe(module_name: str, *, create_app: bool = False) -> dict:
    script = f"""
import importlib
import json
import sys
import types

calls = []

class _Cuda:
    def is_available(self):
        calls.append("torch.cuda.is_available")
        return False
    def device_count(self):
        calls.append("torch.cuda.device_count")
        return 0

_torch = types.ModuleType("torch")
_torch.cuda = _Cuda()
_torch.__version__ = "contract-fake"
_torch.version = types.SimpleNamespace(cuda="contract")
sys.modules["torch"] = _torch

_ct2 = types.ModuleType("ctranslate2")
_ct2.__version__ = "contract-fake"
def _ct2_count():
    calls.append("ctranslate2.get_cuda_device_count")
    return 0
def _ct2_types(device):
    calls.append(f"ctranslate2.get_supported_compute_types:{{device}}")
    return []
_ct2.get_cuda_device_count = _ct2_count
_ct2.get_supported_compute_types = _ct2_types
sys.modules["ctranslate2"] = _ct2

module = importlib.import_module({module_name!r})
if {create_app!r}:
    module.create_app()

forbidden_loaded = sorted(
    name for name in sys.modules
    if name in {{
        "app.asr.service",
        "app.tts.style_bert_vits2_runtime",
        "app.audio.runtime_config",
    }}
)
print(json.dumps({{"calls": calls, "forbidden_loaded": forbidden_loaded}}, sort_keys=True))
"""
    completed = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(script)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(completed.stdout.strip().splitlines()[-1])


def test_app_server_import_does_not_probe_cuda_or_import_audio_runtime():
    result = _run_probe("app.server")

    assert result["calls"] == []
    assert result["forbidden_loaded"] == []


def test_runtime_controls_import_does_not_probe_cuda():
    result = _run_probe("app.api.runtime_controls")

    assert result["calls"] == []
    assert result["forbidden_loaded"] == []


def test_echo_router_import_does_not_load_asr_or_tts_runtime():
    result = _run_probe("app.api.echo")

    assert result["calls"] == []
    assert "app.asr.service" not in result["forbidden_loaded"]
    assert "app.tts.style_bert_vits2_runtime" not in result["forbidden_loaded"]


def test_jobs_router_import_does_not_probe_llm_cuda_or_model_manager():
    result = _run_probe("app.api.jobs")

    assert result["calls"] == []
    assert result["forbidden_loaded"] == []


def test_nexus_router_import_does_not_probe_search_llm_or_cuda():
    result = _run_probe("app.api.nexus")

    assert result["calls"] == []
    assert result["forbidden_loaded"] == []


def test_create_app_router_registration_does_not_probe_cuda_or_audio_runtime():
    result = _run_probe("app.server", create_app=True)

    assert result["calls"] == []
    assert result["forbidden_loaded"] == []


def test_include_routers_keeps_router_imports_lazy_in_app_server_source():
    source = (REPO_ROOT / "app/server.py").read_text(encoding="utf-8")
    prelude = source.split("def include_routers", maxsplit=1)[0]

    assert "from app.api.echo import" not in prelude
    assert "from app.api.jobs import" not in prelude
    assert "from app.api.nexus import" not in prelude
    assert "from app.api.runtime_controls import" not in prelude
    assert "from app.api.echo import router as echo_router" in source.split("def include_routers", maxsplit=1)[1]
