from pathlib import Path


def test_requirements_tts_contract():
    req = Path("requirements-tts.txt").read_text(encoding="utf-8")
    assert "torch==2.11.0+cu128" in req
    assert "torchaudio==2.11.0+cu128" in req
    assert "torch==2.9.1+cu128" not in req
    assert "torchaudio==2.9.1+cu128" not in req
    assert "torchvision==0.24.1+cu128" not in req


def test_dockerfile_torch_python_contract():
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    assert "FROM nvidia/cuda:${CUDA_VERSION}-cudnn-devel-ubuntu${UBUNTU_VERSION}" in dockerfile
    assert "FROM nvidia/cuda:${CUDA_VERSION}-devel-ubuntu${UBUNTU_VERSION}" not in dockerfile
    assert "pytorch/pytorch:2.11.0-cuda12.8-cudnn9-devel" not in dockerfile
    assert "2.9.1" not in dockerfile
    assert "assert sys.version_info[:2] == (3, 11), sys.version" in dockerfile
    assert 'assert torch.__version__.startswith("2.11.0"), torch.__version__' in dockerfile
    assert "deadsnakes" not in dockerfile
    assert "keyserver.ubuntu.com" not in dockerfile
    assert "ppa.launchpadcontent.net/deadsnakes" not in dockerfile
    assert "conda create -n torch_env python=3.11" in dockerfile
    assert "conda install pytorch=2.11.0" not in dockerfile
    assert "--index-url https://download.pytorch.org/whl/cu128" in dockerfile
    assert "torch==2.11.0+cu128" in dockerfile
    assert "torchaudio==2.11.0+cu128" in dockerfile
    assert "python -m venv --system-site-packages /opt/venv" not in dockerfile
    assert "python -m venv --system-site-packages /opt/style-bert-vits2-venv" not in dockerfile
    assert "_pytorch_base_conda.pth" not in dockerfile
    assert "_runpod_opt_venv.pth" not in dockerfile
    assert "base_site_packages" not in dockerfile
    assert 'assert "/opt/venv/" in torch.__file__, torch.__file__' in dockerfile
    assert 'assert "/opt/style-bert-vits2-venv/" in torch.__file__, torch.__file__' in dockerfile
    assert 'assert "/opt/conda/envs/torch_env/lib/python3.11/site-packages" not in paths' in dockerfile
    assert 'assert "/opt/venv/lib/python3.11/site-packages" not in paths' in dockerfile

    py_blocks = _extract_run_python_blocks(dockerfile)
    base_check_block = _find_block_by_print(py_blocks, 'print("base python:", sys.executable)')
    assert 'print("base version:", sys.version)' in base_check_block
    assert "import torch" not in base_check_block
    assert "import torchaudio" not in base_check_block

    first_torch_install = dockerfile.index("torch==2.11.0+cu128")
    first_import_torch = dockerfile.index("import torch")
    assert first_import_torch > first_torch_install


def test_docker_publish_cache_contract():
    workflow = Path(".github/workflows/docker-publish.yml").read_text(encoding="utf-8")
    assert "no-cache: true" not in workflow
    assert "cache-from:" in workflow
    assert "cache-to:" in workflow
    assert "type=gha" in workflow
    assert "type=gha,mode=max" in workflow


def _extract_run_python_blocks(dockerfile: str) -> list[str]:
    blocks: list[str] = []
    marker = "RUN "
    start = 0
    while True:
        idx = dockerfile.find(marker, start)
        if idx == -1:
            break
        end = dockerfile.find("\nRUN ", idx + 1)
        if end == -1:
            end = len(dockerfile)
        block = dockerfile[idx:end]
        if "<<'PY'" in block:
            blocks.append(block)
        start = idx + 1
    return blocks


def _find_block_by_print(blocks: list[str], print_marker: str) -> str:
    for block in blocks:
        if print_marker in block:
            return block
    raise AssertionError(f"missing RUN python block containing {print_marker!r}")
