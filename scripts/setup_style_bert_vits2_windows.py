from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

MIN_BYTES_BY_SUFFIX = {
    ".json": 128,
    ".npy": 256,
    ".safetensors": 1024 * 1024,
    ".bin": 1024 * 1024,
    ".onnx": 1024 * 1024,
}


def _run(cmd: list[str], *, cwd: Path | None = None) -> None:
    print("[RUN]", " ".join(cmd))
    subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True)


def _is_file_ok(path: Path) -> bool:
    if not path.exists() or not path.is_file():
        return False
    threshold = MIN_BYTES_BY_SUFFIX.get(path.suffix.lower(), 1)
    return path.stat().st_size >= threshold


def _download_hf_file(python_exe: Path, repo_id: str, filename: str, local_dir: Path) -> None:
    local_dir.mkdir(parents=True, exist_ok=True)
    expected_path = local_dir / Path(filename).name
    if _is_file_ok(expected_path):
        print(f"[SKIP] Exists: {expected_path}")
        return

    script = (
        "from huggingface_hub import hf_hub_download\n"
        "hf_hub_download(\n"
        f"    repo_id={repo_id!r},\n"
        f"    filename={filename!r},\n"
        f"    local_dir={str(local_dir)!r},\n"
        "    local_dir_use_symlinks=False,\n"
        ")\n"
    )
    _run([str(python_exe), "-c", script])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Setup Style-Bert-VITS2 dedicated Windows venv with DirectML")
    parser.add_argument("--with-directml", action="store_true", help="Install DirectML dependencies")
    parser.add_argument("--force", action="store_true", help="Recreate existing venv")
    parser.add_argument("--skip-model-download", action="store_true", help="Skip initial model downloads")
    parser.add_argument("--skip-repo-clone", action="store_true", help="Skip cloning Style-Bert-VITS2 repo")
    parser.add_argument("--cpu-only", action="store_true", help="Do not install DirectML packages")
    parser.add_argument("--smoke-infer", action="store_true", help="Run DirectML Style-Bert-VITS2 inference smoke test")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parent.parent
    sbv2_repo = repo_root / "third_party" / "Style-Bert-VITS2"
    sbv2_venv = repo_root / "tts_envs" / "style_bert_vits2"
    models_dir = repo_root / "ca_data" / "tts" / "style_bert_vits2" / "models"
    koharune_dir = models_dir / "koharune-ami"

    with_directml = (not args.cpu_only) and (args.with_directml or os.name == "nt")

    if not args.skip_repo_clone and not sbv2_repo.exists():
        sbv2_repo.parent.mkdir(parents=True, exist_ok=True)
        _run([
            "git",
            "clone",
            "--depth",
            "1",
            "https://github.com/litagin02/Style-Bert-VITS2.git",
            str(sbv2_repo),
        ])

    if args.force and sbv2_venv.exists():
        print(f"[INFO] Removing existing venv: {sbv2_venv}")
        shutil.rmtree(sbv2_venv)

    if not sbv2_venv.exists():
        sbv2_venv.parent.mkdir(parents=True, exist_ok=True)
        _run([sys.executable, "-m", "venv", str(sbv2_venv)])

    python_exe = sbv2_venv / "Scripts" / "python.exe"
    pip_exe = sbv2_venv / "Scripts" / "pip.exe"
    if not python_exe.exists():
        python_exe = sbv2_venv / "bin" / "python"
        pip_exe = sbv2_venv / "bin" / "pip"

    _run([str(python_exe), "-m", "pip", "install", "--upgrade", "pip", "wheel", "setuptools<82"])

    if with_directml:
        _run([str(pip_exe), "install", "torch-directml", "onnxruntime-directml"])

    _run([str(python_exe), "-m", "pip", "install", "-e", ".", "--no-deps"], cwd=sbv2_repo)

    _run(
        [
            str(pip_exe),
            "install",
            "numpy<2",
            "numba>=0.59",
            "llvmlite>=0.42",
            "transformers==4.57.3",
            "accelerate>=0.33",
            "safetensors>=0.4",
            "sentencepiece>=0.2",
            "soundfile>=0.12",
            "pyworld-prebuilt",
            "loguru",
            "pyopenjtalk-dict",
            "cmudict",
            "cn2an",
            "g2p_en",
            "GPUtil",
            "gradio>=4.32",
            "jieba",
            "nltk<=3.8.1",
            "num2words",
            "pypinyin",
            "huggingface_hub",
        ]
    )

    try:
        _run([str(pip_exe), "install", "pyopenjtalk"])
    except subprocess.CalledProcessError:
        _run([str(pip_exe), "install", "pyopenjtalk-plus"])

    if not args.skip_model_download:
        _download_hf_file(
            python_exe,
            "ku-nlp/deberta-v2-large-japanese-char-wwm",
            "pytorch_model.bin",
            sbv2_repo / "bert" / "deberta-v2-large-japanese-char-wwm",
        )
        _download_hf_file(
            python_exe,
            "tsukumijima/deberta-v2-large-japanese-char-wwm-onnx",
            "model_fp16.onnx",
            sbv2_repo / "bert" / "deberta-v2-large-japanese-char-wwm-onnx",
        )
        for fn in ["config.json", "style_vectors.npy", "koharune-ami.safetensors"]:
            _download_hf_file(
                python_exe,
                "litagin/sbv2_koharune_ami",
                f"koharune-ami/{fn}",
                models_dir,
            )
        nested_koharune_dir = koharune_dir / "koharune-ami"
        if nested_koharune_dir.is_dir():
            print(f"[INFO] Flattening nested koharune directory: {nested_koharune_dir}")
            for child in nested_koharune_dir.iterdir():
                target = koharune_dir / child.name
                if target.exists():
                    if target.is_file():
                        target.unlink()
                    else:
                        shutil.rmtree(target)
                shutil.move(str(child), str(target))
            shutil.rmtree(nested_koharune_dir, ignore_errors=True)

    smoke = (
        "import torch\n"
        "from style_bert_vits2.tts_model import TTSModel\n"
        "import style_bert_vits2\n"
        "import pyopenjtalk\n"
        "print('imports_ok')\n"
    )
    _run([str(python_exe), "-c", smoke], cwd=sbv2_repo)

    if with_directml:
        dml_smoke = (
            "import torch\n"
            "import torch_directml\n"
            "dml = torch_directml.device()\n"
            "x = torch.ones((2,2), device=dml)\n"
            "y = x + x\n"
            "print(y.cpu())\n"
        )
        _run([str(python_exe), "-c", dml_smoke], cwd=sbv2_repo)
        if args.smoke_infer:
            dml_infer_smoke = (
                "import traceback\n"
                "import torch_directml\n"
                "from style_bert_vits2.tts_model import TTSModel\n"
                "from style_bert_vits2.constants import Languages\n"
                "from pathlib import Path\n"
                f"model_dir = Path({str(koharune_dir)!r})\n"
                "try:\n"
                "    device = torch_directml.device()\n"
                "    model = TTSModel(\n"
                "        model_path=model_dir / 'koharune-ami.safetensors',\n"
                "        config_path=model_dir / 'config.json',\n"
                "        style_vec_path=model_dir / 'style_vectors.npy',\n"
                "        device=device,\n"
                "    )\n"
                "    result = model.infer(text='こんにちは。', language=Languages.JP, style='Neutral')\n"
                "    if result is None:\n"
                "        raise RuntimeError('infer returned None')\n"
                "    print('[OK] DirectML inference ready')\n"
                "except Exception as e:\n"
                "    print('[ERROR] torch_directml import succeeded, but SBV2 DirectML inference failed')\n"
                "    print(f'[ERROR] {type(e).__name__}: {e}')\n"
                "    traceback.print_exc()\n"
                "    raise\n"
            )
            _run([str(python_exe), "-c", dml_infer_smoke], cwd=sbv2_repo)

    assert (koharune_dir / "config.json").exists()
    assert (koharune_dir / "style_vectors.npy").exists()
    assert (koharune_dir / "koharune-ami.safetensors").exists()
    assert (sbv2_repo / "bert" / "deberta-v2-large-japanese-char-wwm" / "pytorch_model.bin").exists()
    assert (sbv2_repo / "bert" / "deberta-v2-large-japanese-char-wwm-onnx" / "model_fp16.onnx").exists()

    print("[OK] Style-Bert-VITS2 Windows setup completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
