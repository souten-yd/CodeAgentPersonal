# syntax=docker/dockerfile:1.7

########################################
# Prebuilt stage: download llama.cpp CUDA binaries
########################################
ARG CUDA_VERSION=12.8.0
ARG UBUNTU_VERSION=22.04

FROM ubuntu:${UBUNTU_VERSION} AS llama_prebuilt

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update -o Acquire::Retries=3 \
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
ARG VOICEVOX_WHEEL_VARIANT=auto
ARG QWEN3_TTS_REQUIRED=false

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

RUN rm -f /etc/apt/sources.list.d/cuda*.list /etc/apt/sources.list.d/nvidia*.list \
    && apt-get update -o Acquire::Retries=3 \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        git \
        tini \
        libgomp1 \
        libcurl4 \
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
RUN python -m pip install --upgrade pip setuptools wheel

# Copy application source first.
COPY . /app

# Install Python dependencies if present.
RUN if [ -f /app/requirements.txt ]; then \
        python -m pip install -r /app/requirements.txt; \
    else \
        python -m pip install fastapi 'uvicorn[standard]' pydantic requests python-multipart; \
    fi

# Install voicevox_core for Linux x86_64 (optional: VOICEVOX TTS support)
# IMPORTANT: install an explicit wheel URL (CUDA -> CPU fallback).
# Do not use `--find-links ... voicevox_core` here, because pip may pick both
# cpu/cuda candidates and fail resolution.
RUN set -eux; \
    if ! python -c "import voicevox_core" 2>/dev/null; then \
      VV_CUDA="https://github.com/VOICEVOX/voicevox_core/releases/download/0.15.0/voicevox_core-0.15.0%2Bcuda-cp38-abi3-linux_x86_64.whl"; \
      VV_CPU="https://github.com/VOICEVOX/voicevox_core/releases/download/0.15.0/voicevox_core-0.15.0%2Bcpu-cp38-abi3-linux_x86_64.whl"; \
      ORDER=""; \
      case "${VOICEVOX_WHEEL_VARIANT}" in \
        cuda) ORDER="${VV_CUDA} ${VV_CPU}" ;; \
        cpu)  ORDER="${VV_CPU} ${VV_CUDA}" ;; \
        *) \
          if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi -L >/dev/null 2>&1; then \
            ORDER="${VV_CUDA} ${VV_CPU}"; \
          else \
            ORDER="${VV_CPU} ${VV_CUDA}"; \
          fi ;; \
      esac; \
      ok=""; \
      for u in ${ORDER}; do \
        python -m pip uninstall -y voicevox_core >/dev/null 2>&1 || true; \
        if python -m pip install --no-deps "${u}" && python -c "import voicevox_core" >/dev/null 2>&1; then ok="1"; break; fi; \
      done; \
      if [ -z "${ok}" ]; then echo "[WARN] voicevox_core not available. VOICEVOX TTS will be disabled."; fi; \
    fi

# Install ONNX Runtime shared library required by voicevox_core 0.15.x
RUN set -eux; \
    if ! ldconfig -p | grep -q "libonnxruntime.so.1.13.1"; then \
      ORT_TGZ="/tmp/onnxruntime-linux-x64-1.13.1.tgz"; \
      curl -fL --retry 3 --retry-delay 2 \
        "https://github.com/microsoft/onnxruntime/releases/download/v1.13.1/onnxruntime-linux-x64-1.13.1.tgz" \
        -o "${ORT_TGZ}"; \
      mkdir -p /tmp/ort_extract /usr/local/lib/onnxruntime; \
      tar -xzf "${ORT_TGZ}" -C /tmp/ort_extract; \
      ORT_LIB_DIR="$(find /tmp/ort_extract -type d -path '*/onnxruntime-linux-x64-1.13.1/lib' | head -n1)"; \
      test -n "${ORT_LIB_DIR}"; \
      cp -a "${ORT_LIB_DIR}/libonnxruntime.so.1.13.1" /usr/local/lib/onnxruntime/; \
      ln -sf /usr/local/lib/onnxruntime/libonnxruntime.so.1.13.1 /usr/local/lib/libonnxruntime.so.1.13.1; \
      ln -sf /usr/local/lib/onnxruntime/libonnxruntime.so.1.13.1 /usr/local/lib/libonnxruntime.so; \
      ldconfig; \
    fi

# Prepare Open JTalk dictionary for VOICEVOX on Runpod-like path.
# main.py expects: /workspace/ca_data/tts/open_jtalk_dic_utf_8-1.11
RUN set -eux; \
    JTDIR="/workspace/ca_data/tts/open_jtalk_dic_utf_8-1.11"; \
    mkdir -p /workspace/ca_data/tts; \
    if [ ! -d "${JTDIR}" ] || [ -z "$(ls -A "${JTDIR}" 2>/dev/null || true)" ]; then \
      TMP="/tmp/open_jtalk_dic_utf_8-1.11.tar.gz"; \
      URLS="\
https://downloads.sourceforge.net/project/open-jtalk/Dictionary/open_jtalk_dic-1.11/open_jtalk_dic_utf_8-1.11.tar.gz \
https://downloads.sourceforge.net/project/open-jtalk/Dictionary/open_jtalk_dic_utf_8-1.11/open_jtalk_dic_utf_8-1.11.tar.gz"; \
      ok=""; \
      for u in ${URLS}; do \
        if curl -fL --retry 3 --retry-delay 2 "${u}" -o "${TMP}"; then ok="1"; break; fi; \
      done; \
      if [ -n "${ok}" ]; then \
        mkdir -p /tmp/openjtalk_extract; \
        tar -xzf "${TMP}" -C /tmp/openjtalk_extract; \
        FOUND="$(find /tmp/openjtalk_extract -type d -name open_jtalk_dic_utf_8-1.11 | head -n1)"; \
        if [ -n "${FOUND}" ]; then \
          rm -rf "${JTDIR}"; \
          mv "${FOUND}" "${JTDIR}"; \
        fi; \
      fi; \
    fi; \
    if [ ! -d "${JTDIR}" ] || [ -z "$(ls -A "${JTDIR}" 2>/dev/null || true)" ]; then \
      echo "[WARN] Open JTalk dictionary was not prepared at ${JTDIR}. VOICEVOX may require manual setup."; \
    fi

# Install torch/torchaudio and validate Qwen3 TTS runtime deps.
# Prefer CUDA 12.4 wheels, but fall back to CPU wheels in CI/build environments
# where CUDA wheels may be unavailable (e.g., transient index/network issues).
# If install fails, write an explicit status artifact that /tts/status can surface.
RUN set -eux; \
    status_file="/app/qwen3_tts_install_status.json"; \
    if python -c "import transformers, torch, soundfile" >/dev/null 2>&1; then \
      printf '{"ok":true,"source":"preinstalled","error":"","timestamp":"%s"}\n' "$(date -u +%FT%TZ)" > "${status_file}"; \
    else \
      if ( \
          python -m pip install -r /app/requirements-tts.txt --index-url https://download.pytorch.org/whl/cu124 \
          || python -m pip install -r /app/requirements-tts.txt --index-url https://download.pytorch.org/whl/cpu \
        ) \
        && python -m pip install --upgrade "transformers>=4.52" "soundfile>=0.12" \
        && python -c "import transformers, torch, soundfile" >/dev/null 2>&1; then \
        printf '{"ok":true,"source":"docker-install","error":"","timestamp":"%s"}\n' "$(date -u +%FT%TZ)" > "${status_file}"; \
      else \
        err="transformers/torch/soundfile installation failed (Docker build, cu124->cpu fallback attempted)"; \
        printf '{"ok":false,"source":"docker-install","error":"%s","timestamp":"%s"}\n' "${err}" "$(date -u +%FT%TZ)" > "${status_file}"; \
        if [ "${QWEN3_TTS_REQUIRED}" = "true" ]; then \
          echo "[ERROR] ${err}" >&2; \
          exit 1; \
        fi; \
      fi; \
    fi

# Re-pin core framework versions in case optional deps caused downgrades
RUN python -m pip install --upgrade "pydantic>=2.6" "fastapi>=0.110"

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
