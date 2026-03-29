# syntax=docker/dockerfile:1.7

########################################
# Prebuilt stage: download llama.cpp CUDA binaries
########################################
ARG CUDA_VERSION=12.8.0
ARG UBUNTU_VERSION=22.04
FROM ubuntu:${UBUNTU_VERSION} AS llama_prebuilt

ENV DEBIAN_FRONTEND=noninteractive

RUN rm -f /etc/apt/sources.list.d/cuda*.list /etc/apt/sources.list.d/nvidia*.list \
    && apt-get update -o Acquire::Retries=3 \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        jq \
        tar \
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
# Runtime stage: Python + codeAgent + llama.cpp
########################################
FROM nvidia/cuda:${CUDA_VERSION}-cudnn-runtime-ubuntu${UBUNTU_VERSION} AS runtime

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LLAMA_HOST=0.0.0.0 \
    LLAMA_PORT=8080 \
    CODEAGENT_HOST=0.0.0.0 \
    CODEAGENT_PORT=8000 \
    CODEAGENT_APP=main:app \
    SANDBOX_MODE=process \
    LLAMA_SERVER_PATH=/app/llama/bin/llama-server \
    LD_LIBRARY_PATH=/app/llama/lib:/usr/local/lib:${LD_LIBRARY_PATH} \
    NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility

WORKDIR /app

RUN apt-get update -o Acquire::Retries=3 \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        tini \
        libgomp1 \
        libcurl4 \
        libsndfile1 \
        build-essential \
        pkg-config \
        software-properties-common \
        gnupg \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        python3.11 \
        python3.11-venv \
        python3.11-distutils \
    && rm -rf /var/lib/apt/lists/*

RUN python3.11 -m venv /opt/venv
ENV PATH=/opt/venv/bin:${PATH}
RUN python -m pip install --no-cache-dir --upgrade pip setuptools wheel

# Copy application source first.
COPY . /app

# Install Python dependencies if present.
RUN if [ -f /app/requirements.txt ]; then \
        python -m pip install --no-cache-dir -r /app/requirements.txt; \
    else \
        python -m pip install --no-cache-dir fastapi 'uvicorn[standard]' pydantic requests python-multipart; \
    fi

# Install Qwen3-TTS runtime dependencies with CUDA 12.8 aligned PyTorch wheels only.
# Keep TTS deps isolated to reduce conflicts with existing FastAPI/WebUI stack.
RUN set -eux; \
    status_file="/app/qwen3_tts_install_status.json"; \
    verify_imports() { \
      failed=""; \
      for mod in torch torchaudio transformers soundfile qwen_tts; do \
        if ! python -c "import ${mod}" >/dev/null 2>&1; then \
          failed="${failed}${failed:+,}${mod}"; \
        fi; \
      done; \
      if [ -n "${failed}" ]; then \
        echo "${failed}" > /tmp/qwen_tts_failed_imports.txt; \
        return 1; \
      fi; \
      return 0; \
    }; \
    if verify_imports; then \
      printf '{"ok":true,"source":"preinstalled","error":"","timestamp":"%s"}\n' "$(date -u +%FT%TZ)" > "${status_file}"; \
    else \
      python -m pip install --no-cache-dir --upgrade-strategy only-if-needed \
        --index-url "https://download.pytorch.org/whl/cu128" \
        -r /app/requirements-tts.txt; \
      python -m pip install --no-cache-dir --upgrade-strategy only-if-needed \
        --index-url "https://pypi.org/simple" \
        -r /app/requirements-tts-qwen.txt; \
      python -m pip check; \
      if verify_imports; then \
        printf '{"ok":true,"source":"docker-install","error":"","timestamp":"%s"}\n' "$(date -u +%FT%TZ)" > "${status_file}"; \
      else \
        err="qwen-tts dependency installation failed; import failures: $(cat /tmp/qwen_tts_failed_imports.txt)"; \
        printf '{"ok":false,"source":"docker-install","error":"%s","timestamp":"%s"}\n' "${err}" "$(date -u +%FT%TZ)" > "${status_file}"; \
        echo "[ERROR] ${err}" >&2; \
        exit 1; \
      fi; \
    fi

# Remove VOICEVOX-related Python packages to avoid pydantic conflicts.
# Keep shared framework packages intact.
RUN python -m pip uninstall -y voicevox-core voicevox-client pyopenjtalk || true


# Re-pin core framework versions in case optional deps caused downgrades
RUN python -m pip install --no-cache-dir --upgrade "pydantic>=2.6" "fastapi>=0.110"

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

COPY docker/start-services.sh /usr/local/bin/start-services.sh
RUN chmod +x /usr/local/bin/start-services.sh

EXPOSE 8000 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=5 \
  CMD curl -fsS http://127.0.0.1:${CODEAGENT_PORT}/health >/dev/null || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/usr/local/bin/start-services.sh"]
