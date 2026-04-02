#!/usr/bin/env python3
"""LongCat-AudioDiT TTS worker script.

Runs inside the dedicated LongCat venv (separate from the main CodeAgent venv)
to avoid the transformers version conflict:
  - Main venv / Qwen3-TTS: transformers==4.57.3
  - LongCat-AudioDiT:      transformers>=5.3.0

Usage (called by main.py via subprocess):
    python longcat_tts_worker.py \\
        --text "Hello world" \\
        --output-path /tmp/out.wav \\
        --model-dir /workspace/ca_data/tts/longcattts/LongCat-AudioDiT-1B \\
        [--ref-audio /tmp/ref.wav --ref-text "Reference text"] \\
        [--device cuda] [--steps 16] [--cfg-strength 4.0] [--guidance-method cfg] [--seed 1024]

Prints a single JSON line to stdout on completion:
  {"status": "ok", "output": "/tmp/out.wav", "duration_sec": 3.14, "sr": 24000}
  {"status": "error", "error": "..."}
"""

import argparse
import json
import os
import sys
import traceback


def _add_repo_to_path() -> None:
    """Add LongCat repo directory to sys.path so 'audiodit' and 'utils' can be imported."""
    repo_dir = os.environ.get("LONGCAT_REPO_DIR", "")
    if repo_dir and os.path.isdir(repo_dir):
        if repo_dir not in sys.path:
            sys.path.insert(0, repo_dir)
        return
    # Fallback: search common locations
    candidates = [
        # Runpod
        "/workspace/LongCat-AudioDiT",
        # Local: relative to this script's directory (scripts/../ca_data/tts/longcattts/repo)
        os.path.join(os.path.dirname(__file__), "..", "ca_data", "tts", "longcattts", "repo"),
    ]
    for path in candidates:
        path = os.path.normpath(path)
        if os.path.isdir(path) and os.path.isfile(os.path.join(path, "audiodit", "__init__.py")):
            if path not in sys.path:
                sys.path.insert(0, path)
            return


def _out(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="LongCat-AudioDiT TTS worker")
    parser.add_argument("--text", required=True, help="Text to synthesize")
    parser.add_argument("--output-path", required=True, help="Output WAV file path")
    parser.add_argument("--model-dir", required=True, help="HuggingFace model ID or local path")
    parser.add_argument("--ref-audio", default=None, help="Path to reference/prompt audio (for voice cloning)")
    parser.add_argument("--ref-text", default=None, help="Transcript of the reference audio")
    parser.add_argument("--device", default="cuda", choices=["cuda", "cpu"])
    parser.add_argument("--steps", type=int, default=16, help="Number of ODE steps")
    parser.add_argument("--cfg-strength", type=float, default=4.0, help="CFG/APG guidance strength")
    parser.add_argument("--guidance-method", default="cfg", choices=["cfg", "apg"])
    parser.add_argument("--seed", type=int, default=1024)
    args = parser.parse_args()

    try:
        _add_repo_to_path()
        _run(args)
    except Exception as e:
        _out({"status": "error", "error": str(e), "traceback": traceback.format_exc()})
        sys.exit(1)


def _run(args: argparse.Namespace) -> None:
    import numpy as np
    import soundfile as sf
    import torch
    import torch.nn.functional as F

    try:
        import audiodit  # noqa: F401  – registers AudioDiTConfig/AudioDiTModel
        from audiodit import AudioDiTModel
    except ImportError as e:
        _out({"status": "error", "error": f"audiodit import failed: {e}. Run scripts/setup_longcat_tts.sh first."})
        sys.exit(1)

    try:
        from transformers import AutoTokenizer
    except ImportError as e:
        _out({"status": "error", "error": f"transformers import failed: {e}"})
        sys.exit(1)

    try:
        from utils import normalize_text, load_audio, approx_duration_from_text
    except ImportError as e:
        _out({"status": "error", "error": f"utils import failed: {e}. Ensure LONGCAT_REPO_DIR is set correctly."})
        sys.exit(1)

    torch.backends.cudnn.benchmark = False
    device_str = args.device
    if device_str == "cuda" and not torch.cuda.is_available():
        print("[LongCat-TTS][warn] CUDA unavailable, falling back to CPU", file=sys.stderr)
        device_str = "cpu"
    device = torch.device(device_str)

    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed(args.seed)

    # Load model
    model = AudioDiTModel.from_pretrained(args.model_dir).to(device)
    model.vae.to_half()
    model.eval()
    tokenizer = AutoTokenizer.from_pretrained(model.config.text_encoder_model)

    sr = model.config.sampling_rate
    full_hop = model.config.latent_hop
    max_duration = model.config.max_wav_duration

    # Text preparation
    text = normalize_text(args.text)
    has_prompt = args.ref_audio is not None and os.path.isfile(args.ref_audio)

    if has_prompt:
        prompt_text = normalize_text(args.ref_text or "")
        sep = " " if (prompt_text and prompt_text[-1] != ".") else ""
        full_text = f"{prompt_text}{sep}{text}" if prompt_text else text
    else:
        full_text = text

    inputs = tokenizer([full_text], padding="longest", return_tensors="pt")
    inputs = {k: v.to(device) for k, v in inputs.items()}

    # Prompt audio
    prompt_wav = None
    prompt_dur = 0
    if has_prompt:
        prompt_wav = load_audio(args.ref_audio, sr).unsqueeze(0)
        off = 3
        pw = load_audio(args.ref_audio, sr)
        if pw.shape[-1] % full_hop != 0:
            pw = F.pad(pw, (0, full_hop - pw.shape[-1] % full_hop))
        pw = F.pad(pw, (0, full_hop * off))
        with torch.no_grad():
            plt = model.vae.encode(pw.unsqueeze(0).to(device))
        if off:
            plt = plt[..., :-off]
        prompt_dur = plt.shape[-1]

    # Duration estimation
    prompt_time = prompt_dur * full_hop / sr
    dur_sec = approx_duration_from_text(text, max_duration=max_duration - prompt_time)
    if has_prompt and args.ref_text:
        prompt_text_norm = normalize_text(args.ref_text)
        approx_pd = approx_duration_from_text(prompt_text_norm, max_duration=max_duration)
        if approx_pd > 0:
            ratio = float(np.clip(prompt_time / approx_pd, 1.0, 1.5))
            dur_sec = dur_sec * ratio

    duration = int(dur_sec * sr // full_hop)
    duration = min(duration + prompt_dur, int(max_duration * sr // full_hop))

    # Generate
    with torch.no_grad():
        output = model(
            input_ids=inputs["input_ids"],
            attention_mask=inputs["attention_mask"],
            prompt_audio=prompt_wav,
            duration=duration,
            steps=args.steps,
            cfg_strength=args.cfg_strength,
            guidance_method=args.guidance_method,
        )

    wav = output.waveform.squeeze().detach().cpu().numpy()
    os.makedirs(os.path.dirname(os.path.abspath(args.output_path)), exist_ok=True)
    sf.write(args.output_path, wav, sr)

    _out({
        "status": "ok",
        "output": args.output_path,
        "duration_sec": round(len(wav) / sr, 3),
        "sr": sr,
        "device": device_str,
        "steps": args.steps,
        "guidance_method": args.guidance_method,
    })


if __name__ == "__main__":
    main()
