# syntax=docker/dockerfile:1.7

########################################
# Prebuilt stage: download llama.cpp CUDA binaries
########################################
ARG CUDA_VERSION=12.8.0
ARG UBUNTU_VERSION=22.04
FROM ubuntu:${UBUNTU_VERSION} AS llama_prebuilt

ENV DEBIAN_FRONTEND=noninteractive

RUN rm -f /etc/apt/sources.list.d/cuda*.list /etc/apt/sources.list.d/nvidia*.list \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get update -o Acquire::Retries=5 \
    && apt-get install -y --no-install-recommends --fix-missing \
        ca-certificates \
        curl \
        jq \
        tar \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    ASSET_REGEX='^llama\.cpp-b[0-9]+-cuda-12\.8\.tar\.gz$'; \
    curl -fsSL https://api.github.com/repos/ai-dock/llama.cpp-cuda/releases/latest -o /tmp/release.json; \
    ASSET_URL="$(jq -r --arg re "${ASSET_REGEX}" '.assets[] | select(.name | test($re)) | .browser_download_url' /tmp/release.json | head -n1)"; \
    ASSET_NAME="$(jq -r --arg re "${ASSET_REGEX}" '.assets[] | select(.name | test($re)) | .name' /tmp/release.json | head -n1)"; \
    test "${ASSET_URL}" != "null"; \
    test "${ASSET_NAME}" != "null"; \
    test -n "${ASSET_URL}"; \
    test -n "${ASSET_NAME}"; \
    curl -fL "${ASSET_URL}" -o "/tmp/${ASSET_NAME}"; \
    mkdir -p /tmp/extract; \
    tar -xzf "/tmp/${ASSET_NAME}" -C /tmp/extract; \
    SOURCE_ROOT="$(dirname "$(find /tmp/extract -type f -name llama-server -perm -u+x | head -n1)")"; \
    test -n "${SOURCE_ROOT}"; \
    mkdir -p /out/bin /out/lib; \
    cp -a "${SOURCE_ROOT}/llama-server" /out/bin/llama-server; \
    cp -a "${SOURCE_ROOT}/llama-cli" /out/bin/llama-cli; \
    find "${SOURCE_ROOT}" \( -type f -o -type l \) -name '*.so*' -exec cp -a {} /out/lib/ \;

########################################
## Build stage: Python deps + Style-Bert-VITS2 prep (with CUDA toolkit)
########################################
FROM nvidia/cuda:${CUDA_VERSION}-cudnn-devel-ubuntu${UBUNTU_VERSION} AS py_base

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONIOENCODING=utf-8 \
    HF_HOME=/opt/hf_cache \
    HUGGINGFACE_HUB_CACHE=/opt/hf_cache/hub \
    TRANSFORMERS_CACHE=/opt/hf_cache/transformers \
    XDG_CACHE_HOME=/opt/cache \
    CODEAGENT_STYLE_BERT_VITS2_REPO_DIR=/app/Style-Bert-VITS2 \
    CODEAGENT_STYLE_BERT_VITS2_VENV_DIR=/opt/style-bert-vits2-venv \
    CODEAGENT_STYLE_BERT_VITS2_BASE_DIR=/workspace/ca_data/tts/style_bert_vits2 \
    CODEAGENT_STYLE_BERT_VITS2_MODELS_DIR=/workspace/ca_data/tts/style_bert_vits2/models \
    CODEAGENT_ASR_DEFAULT_MODEL=large-v3-turbo \
    CODEAGENT_ASR_MODEL_CACHE=/opt/asr_models \
    CODEAGENT_ASR_MODEL_PATH=/opt/asr_models/large-v3-turbo \
    CODEAGENT_ASR_LOCAL_FILES_ONLY=1

WORKDIR /app

COPY docker/keys/deadsnakes.gpg /etc/apt/keyrings/deadsnakes.gpg

RUN mkdir -p \
    /opt/cache \
    /opt/hf_cache \
    /opt/hf_cache/hub \
    /opt/hf_cache/transformers \
    /opt/style-bert-vits2-models

RUN rm -rf /var/lib/apt/lists/* \
    && apt-get update -o Acquire::Retries=5 \
    && apt-get install -y --no-install-recommends --fix-missing \
        ca-certificates \
        curl \
        jq \
        build-essential \
        pkg-config \
        sox \
        libsox-fmt-all \
    && update-ca-certificates \
    && test -s /etc/apt/keyrings/deadsnakes.gpg \
    && gpg --show-keys --with-colons /etc/apt/keyrings/deadsnakes.gpg | grep -q "BA6932366A755776" \
    && . /etc/os-release \
    && echo "deb [signed-by=/etc/apt/keyrings/deadsnakes.gpg] https://ppa.launchpadcontent.net/deadsnakes/ppa/ubuntu ${VERSION_CODENAME} main" \
        > /etc/apt/sources.list.d/deadsnakes.list \
    && apt-get update -o Acquire::Retries=5 \
    && apt-get install -y --no-install-recommends --fix-missing \
        python3.11 \
        python3.11-dev \
        python3.11-venv \
        python3.11-distutils \
    && rm -rf /var/lib/apt/lists/*

RUN python3.11 -m venv /opt/venv
ENV PATH=/opt/venv/bin:${PATH}
RUN python -m pip install --no-cache-dir --upgrade pip setuptools wheel

FROM py_base AS py_build

# Copy application source first.
COPY . /app

# Install Python dependencies if present.
RUN if [ -f /app/requirements.txt ]; then \
        python -m pip install --no-cache-dir -r /app/requirements.txt; \
    else \
        python -m pip install --no-cache-dir fastapi 'uvicorn[standard]' pydantic requests python-multipart; \
    fi


# Pre-download bundled faster-whisper ASR model into image layer.
RUN set -eux; \
    mkdir -p /opt/asr_models/large-v3-turbo; \
    python - <<'PY'
from pathlib import Path

model_dir = Path("/opt/asr_models/large-v3-turbo")
model_dir.mkdir(parents=True, exist_ok=True)

try:
    from faster_whisper.utils import download_model
    try:
        download_model("large-v3-turbo", output_dir=str(model_dir))
    except TypeError:
        download_model("large-v3-turbo", cache_dir="/opt/asr_models")
except Exception:
    from faster_whisper import WhisperModel
    WhisperModel(
        "large-v3-turbo",
        device="cpu",
        compute_type="int8",
        download_root="/opt/asr_models",
    )

print("[ASR] faster-whisper large-v3-turbo download step completed")
PY

# Install TTS runtime dependencies (Style-Bert-VITS2 required set).
RUN set -eux; \
    python -m pip install --no-cache-dir --upgrade-strategy only-if-needed \
      --index-url "https://download.pytorch.org/whl/cu128" \
      -r /app/requirements-tts.txt; \
    python -m pip check

# Re-pin core framework versions in case optional deps caused downgrades
RUN python -m pip install --no-cache-dir --upgrade "pydantic>=2.6" "fastapi>=0.110"

########################################
# Build stage: Style-Bert-VITS2 (isolated venv/layer)
########################################
FROM py_build AS style_bert_vits2_build

ARG STYLE_BERT_VITS2_REPO_URL="https://github.com/litagin02/Style-Bert-VITS2.git"
ARG STYLE_BERT_VITS2_REF="master"

RUN mkdir -p \
    /opt/cache \
    /opt/hf_cache \
    /opt/hf_cache/hub \
    /opt/hf_cache/transformers \
    /opt/style-bert-vits2-models \
    /app/Style-Bert-VITS2/bert/deberta-v2-large-japanese-char-wwm \
    /app/Style-Bert-VITS2/bert/deberta-v2-large-japanese-char-wwm-onnx

RUN rm -rf /var/lib/apt/lists/* \
    && apt-get update -o Acquire::Retries=5 \
    && apt-get install -y --no-install-recommends --fix-missing \
        git \
    && rm -rf /var/lib/apt/lists/*

RUN rm -rf /app/Style-Bert-VITS2 \
    && git clone --depth 1 --branch "${STYLE_BERT_VITS2_REF}" "${STYLE_BERT_VITS2_REPO_URL}" /app/Style-Bert-VITS2

# Keep Style-Bert-VITS2 dependencies isolated from existing Qwen3-TTS pins by using a dedicated venv.
RUN set -eux; \
    cd /app/Style-Bert-VITS2; \
    python3.11 -m venv /opt/style-bert-vits2-venv; \
    site_packages="$("/opt/style-bert-vits2-venv/bin/python" -c 'import site; print(site.getsitepackages()[0])')"; \
    printf '%s\n' \
      '/opt/venv/lib/python3.11/site-packages' \
      '/opt/venv/local/lib/python3.11/dist-packages' \
      '/opt/venv/lib/python3/dist-packages' \
      '/opt/venv/lib/python3.11/dist-packages' \
      > "${site_packages}/_runpod_opt_venv.pth"; \
    /opt/style-bert-vits2-venv/bin/python -m pip install --no-cache-dir --upgrade pip wheel "setuptools<82"; \
    /opt/style-bert-vits2-venv/bin/python -m pip install --no-cache-dir huggingface_hub; \
    /opt/style-bert-vits2-venv/bin/python -c "import torch, torchaudio, av; print(torch.__version__, torchaudio.__version__, av.__version__)"; \
    /opt/style-bert-vits2-venv/bin/python -m pip install --no-cache-dir -e . --no-deps; \
    /opt/style-bert-vits2-venv/bin/python -m pip install --no-cache-dir \
      "numpy<2" \
      "numba>=0.59" \
      "llvmlite>=0.42" \
      "transformers==4.57.3" \
      "accelerate>=0.33" \
      "safetensors>=0.4" \
      "sentencepiece>=0.2" \
      "soundfile>=0.12" \
      pyworld-prebuilt \
      loguru \
      pyopenjtalk-dict \
      cmudict \
      cn2an \
      g2p_en \
      GPUtil \
      "gradio>=4.32" \
      jieba \
      "nltk<=3.8.1" \
      num2words \
      pypinyin; \
    /opt/style-bert-vits2-venv/bin/python -c "import pyopenjtalk; pyopenjtalk.g2p('辞書ウォームアップ')"

RUN set -eux; \
    mkdir -p \
      /app/Style-Bert-VITS2/bert/deberta-v2-large-japanese-char-wwm \
      /app/Style-Bert-VITS2/bert/deberta-v2-large-japanese-char-wwm-onnx \
      /opt/style-bert-vits2-models; \
    /opt/style-bert-vits2-venv/bin/python - <<'PY'
from huggingface_hub import hf_hub_download
from pathlib import Path

hf_hub_download(repo_id="ku-nlp/deberta-v2-large-japanese-char-wwm", filename="pytorch_model.bin", local_dir="/app/Style-Bert-VITS2/bert/deberta-v2-large-japanese-char-wwm", local_dir_use_symlinks=False)
hf_hub_download(repo_id="tsukumijima/deberta-v2-large-japanese-char-wwm-onnx", filename="model_fp16.onnx", local_dir="/app/Style-Bert-VITS2/bert/deberta-v2-large-japanese-char-wwm-onnx", local_dir_use_symlinks=False)
for fn in ["koharune-ami/config.json", "koharune-ami/style_vectors.npy", "koharune-ami/koharune-ami.safetensors"]:
    hf_hub_download(repo_id="litagin/sbv2_koharune_ami", filename=fn, local_dir="/opt/style-bert-vits2-models", local_dir_use_symlinks=False)
PY

RUN set -eux; \
    test -x /opt/style-bert-vits2-venv/bin/python; \
    test -d /opt/cache; \
    test -d /opt/hf_cache; \
    test -d /opt/hf_cache/hub; \
    test -d /opt/style-bert-vits2-models; \
    test -f /app/Style-Bert-VITS2/bert/deberta-v2-large-japanese-char-wwm/pytorch_model.bin; \
    test -f /app/Style-Bert-VITS2/bert/deberta-v2-large-japanese-char-wwm-onnx/model_fp16.onnx; \
    test -f /opt/style-bert-vits2-models/koharune-ami/config.json; \
    test -f /opt/style-bert-vits2-models/koharune-ami/style_vectors.npy; \
    test -f /opt/style-bert-vits2-models/koharune-ami/koharune-ami.safetensors; \
    /opt/style-bert-vits2-venv/bin/python - <<'PY'
import torch
import transformers
import accelerate
import safetensors
import sentencepiece
import soundfile
import numba
import llvmlite
from style_bert_vits2.tts_model import TTSModel

print("SBV2 deps OK")
print("torch", torch.__version__, torch.__file__)
print("transformers", transformers.__version__, transformers.__file__)
print("accelerate", accelerate.__version__, accelerate.__file__)
print("safetensors", safetensors.__version__, safetensors.__file__)
print("sentencepiece", sentencepiece.__version__, sentencepiece.__file__)
print("soundfile", soundfile.__version__, soundfile.__file__)
print("numba", numba.__version__)
print("llvmlite", llvmlite.__version__)
PY

########################################
# Runtime stage: Python + codeAgent + llama.cpp
########################################
FROM nvidia/cuda:${CUDA_VERSION}-cudnn-runtime-ubuntu${UBUNTU_VERSION} AS runtime

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONIOENCODING=utf-8 \
    LLAMA_HOST=0.0.0.0 \
    LLAMA_PORT=8080 \
    CODEAGENT_HOST=0.0.0.0 \
    CODEAGENT_PORT=8000 \
    CODEAGENT_APP=main:app \
    DEFAULT_LLM_CTX_SIZE=16384 \
    LLAMA_CTX_SIZE=16384 \
    NEXUS_ANSWER_LLM_MAX_CONTEXT_TOKENS=16384 \
    SANDBOX_MODE=process \
    LLAMA_SERVER_PATH=/app/llama/bin/llama-server \
    LD_LIBRARY_PATH=/app/llama/lib:/usr/local/lib:${LD_LIBRARY_PATH} \
    NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility \
    HF_HOME=/opt/hf_cache \
    HUGGINGFACE_HUB_CACHE=/opt/hf_cache/hub \
    TRANSFORMERS_CACHE=/opt/hf_cache/transformers \
    XDG_CACHE_HOME=/opt/cache \
    CODEAGENT_STYLE_BERT_VITS2_REPO_DIR=/app/Style-Bert-VITS2 \
    CODEAGENT_STYLE_BERT_VITS2_VENV_DIR=/opt/style-bert-vits2-venv \
    CODEAGENT_STYLE_BERT_VITS2_BASE_DIR=/workspace/ca_data/tts/style_bert_vits2 \
    CODEAGENT_STYLE_BERT_VITS2_MODELS_DIR=/workspace/ca_data/tts/style_bert_vits2/models \
    CODEAGENT_ASR_DEFAULT_MODEL=large-v3-turbo \
    CODEAGENT_ASR_MODEL_CACHE=/opt/asr_models \
    CODEAGENT_ASR_MODEL_PATH=/opt/asr_models/large-v3-turbo \
    CODEAGENT_ASR_LOCAL_FILES_ONLY=1

WORKDIR /app

COPY docker/keys/deadsnakes.gpg /etc/apt/keyrings/deadsnakes.gpg

RUN rm -rf /var/lib/apt/lists/* \
    && apt-get update -o Acquire::Retries=5 \
    && apt-get install -y --no-install-recommends --fix-missing \
        build-essential \
        ca-certificates \
        curl \
        git \
        tini \
        libgomp1 \
        libcurl4 \
        libffi-dev \
        libsndfile1 \
        libssl-dev \
        libxml2 \
        libxslt-dev \
        zlib1g-dev \
        sox \
        libsox-fmt-all \
    && update-ca-certificates \
    && test -s /etc/apt/keyrings/deadsnakes.gpg \
    && gpg --show-keys --with-colons /etc/apt/keyrings/deadsnakes.gpg | grep -q "BA6932366A755776" \
    && . /etc/os-release \
    && echo "deb [signed-by=/etc/apt/keyrings/deadsnakes.gpg] https://ppa.launchpadcontent.net/deadsnakes/ppa/ubuntu ${VERSION_CODENAME} main" \
        > /etc/apt/sources.list.d/deadsnakes.list \
    && apt-get update -o Acquire::Retries=5 \
    && apt-get install -y --no-install-recommends --fix-missing \
        python3.11 \
        python3.11-venv \
        python3.11-distutils \
    && rm -rf /var/lib/apt/lists/*

RUN python3.11 -m venv /opt/venv
ENV PATH=/opt/venv/bin:${PATH}

# Copy application source and prebuilt venv artifacts from build stage.
COPY . /app
COPY --from=py_build /opt/venv /opt/venv
COPY --from=style_bert_vits2_build /app/Style-Bert-VITS2 /app/Style-Bert-VITS2
COPY --from=style_bert_vits2_build /opt/style-bert-vits2-venv /opt/style-bert-vits2-venv
COPY --from=style_bert_vits2_build /opt/hf_cache /opt/hf_cache
COPY --from=style_bert_vits2_build /opt/cache /opt/cache
COPY --from=style_bert_vits2_build /opt/style-bert-vits2-models /opt/style-bert-vits2-models
COPY --from=py_build /opt/asr_models /opt/asr_models

# Build SearXNG editable runtime inside isolated venv for Runpod single-container startup.
RUN set -eux; \
    mkdir -p /opt/searxng; \
    git clone https://github.com/searxng/searxng /opt/searxng/searxng-src; \
    python3.11 -m venv /opt/searxng/searx-pyenv; \
    /opt/searxng/searx-pyenv/bin/pip install --no-cache-dir -U pip setuptools wheel; \
    /opt/searxng/searx-pyenv/bin/pip install --no-cache-dir -U pyyaml msgspec typing-extensions pybind11; \
    cd /opt/searxng/searxng-src; \
    /opt/searxng/searx-pyenv/bin/pip install --no-cache-dir --use-pep517 --no-build-isolation -e .

# Copy compiled llama artifacts into the paths the app expects.
RUN mkdir -p /app/llama/bin /app/llama/lib /models
COPY --from=llama_prebuilt /out/bin/llama-server /app/llama/bin/llama-server
COPY --from=llama_prebuilt /out/bin/llama-cli /app/llama/bin/llama-cli
COPY --from=llama_prebuilt /out/lib/ /app/llama/lib/

# Compatibility symlinks for apps that look in different places.
RUN ln -sf /app/llama/bin/llama-server /usr/local/bin/llama-server \
    && ln -sf /app/llama/bin/llama-cli /usr/local/bin/llama-cli \
    && ln -sf /app/llama/bin/llama-server /app/llama/llama-server \
    && ln -sf /app/llama/bin/llama-server /app/llama/llama-server.exe \
    && ln -sf /app/llama/bin/llama-cli /app/llama/llama-cli \
    && ldconfig

RUN set -eux; \
    mkdir -p /models; \
    python - <<'PY'
from huggingface_hub import hf_hub_download
from pathlib import Path

dst = hf_hub_download(
    repo_id="unsloth/gemma-4-E4B-it-GGUF",
    filename="gemma-4-E4B-it-Q4_K_M.gguf",
    local_dir="/models",
    local_dir_use_symlinks=False,
)
print(f"[LLM] bundled GGUF downloaded: {dst}")
p = Path("/models/gemma-4-E4B-it-Q4_K_M.gguf")
if not p.exists() or p.stat().st_size < 100 * 1024 * 1024:
    raise RuntimeError(f"GGUF download failed or too small: {p}")
PY

COPY docker/start-services.sh /usr/local/bin/start-services.sh
RUN chmod +x /usr/local/bin/start-services.sh

EXPOSE 8000 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=5 \
  CMD curl -fsS http://127.0.0.1:${CODEAGENT_PORT}/health >/dev/null || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/usr/local/bin/start-services.sh"]
