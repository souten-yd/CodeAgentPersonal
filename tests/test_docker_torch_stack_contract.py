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
    assert "2.9.1" not in dockerfile
    assert "assert sys.version_info[:2] == (3, 11), sys.version" in dockerfile
    assert 'assert torch.__version__.startswith("2.11.0"), torch.__version__' in dockerfile
    assert "deadsnakes" not in dockerfile
    assert "keyserver.ubuntu.com" not in dockerfile
    assert "ppa.launchpadcontent.net/deadsnakes" not in dockerfile


def test_docker_publish_cache_contract():
    workflow = Path(".github/workflows/docker-publish.yml").read_text(encoding="utf-8")
    assert "no-cache: true" not in workflow
    assert "cache-from: type=gha" in workflow
    assert "cache-to: type=gha,mode=max" in workflow
