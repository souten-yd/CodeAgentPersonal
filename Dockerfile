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
# Build stage: Python deps + Qwen3-TTS + flash-attn build (with CUDA toolkit)
########################################
FROM nvidia/cuda:${CUDA_VERSION}-cudnn-devel-ubuntu${UBUNTU_VERSION} AS tts_build

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONIOENCODING=utf-8 \
    INSTALL_FLASH_ATTN=1 \
    REQUIRE_FLASH_ATTN=0 \
    FLASH_ATTN_MAX_JOBS=""

WORKDIR /app

RUN apt-get update -o Acquire::Retries=3 \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        jq \
        build-essential \
        pkg-config \
        software-properties-common \
        gnupg \
        sox \
        libsox-fmt-all \
    && update-ca-certificates \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        python3.11 \
        python3.11-dev \
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
    flash_attn_log="/tmp/flash_attn_install.log"; \
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
      sox_available=false; \
      if command -v sox >/dev/null 2>&1; then sox_available=true; fi; \
      flash_attn_available=false; \
      if python -c "import flash_attn" >/dev/null 2>&1; then flash_attn_available=true; fi; \
      printf '{"ok":true,"source":"preinstalled","error":"","timestamp":"%s","sox_available":%s,"flash_attn_attempted":false,"flash_attn_available":%s,"flash_attn_error":""}\n' "$(date -u +%FT%TZ)" "${sox_available}" "${flash_attn_available}" > "${status_file}"; \
    else \
      python -m pip install --no-cache-dir --upgrade-strategy only-if-needed \
        --index-url "https://download.pytorch.org/whl/cu128" \
        -r /app/requirements-tts.txt; \
      python -m pip install --no-cache-dir --upgrade-strategy only-if-needed \
        --index-url "https://pypi.org/simple" \
        -r /app/requirements-tts-qwen.txt; \
      python -c "import torch, torchaudio; print(torch.__version__, torch.version.cuda, torchaudio.__version__)"; \
      python -m pip check; \
      if verify_imports; then \
        sox_available=false; \
        if command -v sox >/dev/null 2>&1; then sox_available=true; fi; \
        flash_attn_attempted=false; \
        flash_attn_available=false; \
        flash_attn_source="not-installed"; \
        flash_attn_error=""; \
        flash_attn_error_detail=""; \
        flash_attn_error_detail_summary=""; \
        flash_attn_error_detail_path=""; \
        has_cuda_env=false; \
        if [ -d "/usr/local/cuda" ] || command -v nvidia-smi >/dev/null 2>&1 || command -v nvcc >/dev/null 2>&1; then has_cuda_env=true; fi; \
        echo "[Qwen3-TTS][build] flash-attn environment: has_cuda_env=${has_cuda_env}"; \
        if [ "${INSTALL_FLASH_ATTN:-1}" = "1" ] && [ "${has_cuda_env}" = "true" ]; then \
          python -m pip install --no-cache-dir packaging psutil ninja; \
          python -m pip show packaging psutil ninja; \
          echo "[Qwen3-TTS][build] ninja version check"; \
          ninja --version; \
          echo "[Qwen3-TTS][build] nvcc path check"; \
          which nvcc; \
          echo "[Qwen3-TTS][build] nvcc version check"; \
          nvcc --version; \
          echo "[Qwen3-TTS][build] torch/cuda check"; \
          python -c "import torch; print(torch.__version__, torch.version.cuda)"; \
          flash_attn_attempted=true; \
          rm -f "${flash_attn_log}"; \
          flash_release_api="https://api.github.com/repos/mjun0812/flash-attention-prebuild-wheels/releases/tags/v0.9.4"; \
          flash_asset_list="/tmp/flash_attn_release_assets.txt"; \
          flash_wheel_url=""; \
          echo "[Qwen3-TTS][build] resolving flash-attn prebuilt wheel from v0.9.4"; \
          if curl -fsSL "${flash_release_api}" -o /tmp/flash_attn_release.json; then \
            flash_candidates_cp311_file="/tmp/flash_attn_candidates_cp311.txt"; \
            flash_candidates_torch_file="/tmp/flash_attn_candidates_torch211.txt"; \
            flash_candidates_platform_file="/tmp/flash_attn_candidates_linux_x86_64.txt"; \
            jq -r '.assets[].browser_download_url' /tmp/flash_attn_release.json | tee "${flash_asset_list}" > /dev/null || true; \
            echo "[Qwen3-TTS][build] flash-attn release asset URLs (first 20 from jq):"; \
            sed -n '1,20p' "${flash_asset_list}" || true; \
            grep -Ei 'cp311' "${flash_asset_list}" > "${flash_candidates_cp311_file}" || true; \
            echo "[Qwen3-TTS][build] flash-attn candidates after cp311 filter:"; \
            if [ -s "${flash_candidates_cp311_file}" ]; then cat "${flash_candidates_cp311_file}"; else echo "(none)"; fi; \
            grep -Ei 'torch(2[._-]?11|211)|pytorch(2[._-]?11|211)' "${flash_candidates_cp311_file}" > "${flash_candidates_torch_file}" || true; \
            echo "[Qwen3-TTS][build] flash-attn candidates after torch 2.11 filter:"; \
            if [ -s "${flash_candidates_torch_file}" ]; then cat "${flash_candidates_torch_file}"; else echo "(none)"; fi; \
            grep -Ei 'linux_x86_64' "${flash_candidates_torch_file}" | sort -u > "${flash_candidates_platform_file}" || true; \
            echo "[Qwen3-TTS][build] flash-attn candidates after Linux x86_64 filter (sorted):"; \
            if [ -s "${flash_candidates_platform_file}" ]; then cat "${flash_candidates_platform_file}"; else echo "(none)"; fi; \
            flash_assets="$(cat "${flash_candidates_torch_file}")"; \
            if [ -z "${flash_wheel_url}" ]; then \
              flash_wheel_url="$(printf '%s\n' "${flash_assets}" | grep -Ei 'flash_attn-2\.8\.3' | grep -Ei 'cu128' | grep -Ei 'linux_x86_64' | head -n1)"; \
            fi; \
            if [ -z "${flash_wheel_url}" ]; then \
              flash_wheel_url="$(printf '%s\n' "${flash_assets}" | grep -Ei 'flash_attn-2\.8\.3' | grep -Ei 'cu128' | grep -Ei 'manylinux.*x86_64' | head -n1)"; \
            fi; \
            if [ -z "${flash_wheel_url}" ]; then \
              flash_wheel_url="$(printf '%s\n' "${flash_assets}" | grep -Ei 'flash_attn-2\.7\.4' | grep -Ei 'cu128' | grep -Ei 'linux_x86_64' | head -n1)"; \
            fi; \
            if [ -z "${flash_wheel_url}" ]; then \
              flash_wheel_url="$(printf '%s\n' "${flash_assets}" | grep -Ei 'flash_attn-2\.7\.4' | grep -Ei 'cu128' | grep -Ei 'manylinux.*x86_64' | head -n1)"; \
            fi; \
            if [ -z "${flash_wheel_url}" ]; then \
              flash_wheel_url="$(printf '%s\n' "${flash_assets}" | grep -Ei 'flash_attn-2\.6\.3' | grep -Ei 'cu128' | grep -Ei 'linux_x86_64' | head -n1)"; \
            fi; \
            if [ -z "${flash_wheel_url}" ]; then \
              flash_wheel_url="$(printf '%s\n' "${flash_assets}" | grep -Ei 'flash_attn-2\.(8\.3|7\.4|6\.3)' | grep -Ei 'cu126' | grep -Ei 'linux_x86_64|manylinux.*x86_64' | head -n1)"; \
            fi; \
            if [ -z "${flash_wheel_url}" ]; then \
              echo "[Qwen3-TTS][build] no prebuilt wheel candidate found. asset list kept at ${flash_asset_list}"; \
            fi; \
          else \
            echo "[Qwen3-TTS][build] warning: failed to fetch ${flash_release_api}"; \
          fi; \
          install_and_import_ok=false; \
          echo "[Qwen3-TTS][build] flash-attn selected prebuilt URL: ${flash_wheel_url:-<none>}"; \
          if [ -n "${flash_wheel_url}" ]; then \
            flash_attn_source="prebuilt-wheel(v0.9.4)"; \
            if python -m pip install --no-cache-dir "${flash_wheel_url}" 2>&1 | tee "${flash_attn_log}" && python -c "import flash_attn" >/dev/null 2>&1; then \
              install_and_import_ok=true; \
            fi; \
          fi; \
          if [ "${install_and_import_ok}" != "true" ]; then \
            flash_attn_source="source-build"; \
            source_jobs="${FLASH_ATTN_MAX_JOBS:-1}"; \
            flash_cmd="MAX_JOBS=${source_jobs} python -m pip install -v flash-attn --no-build-isolation"; \
            echo "[Qwen3-TTS][build] flash-attn fallback install command: ${flash_cmd}"; \
            if bash -o pipefail -c "${flash_cmd} 2>&1 | tee '${flash_attn_log}'" && python -c "import flash_attn" >/dev/null 2>&1; then \
              install_and_import_ok=true; \
            fi; \
          fi; \
          if [ "${install_and_import_ok}" != "true" ]; then \
            flash_attn_error="flash-attn install failed"; \
            flash_attn_error_detail="$(cat "${flash_attn_log}")"; \
            flash_attn_error_detail_summary="${flash_attn_error_detail}"; \
            flash_attn_log_size="$(wc -c < "${flash_attn_log}")"; \
            if [ "${flash_attn_log_size}" -gt 12000 ]; then \
              mkdir -p /app/logs; \
              flash_attn_error_detail_path="/app/logs/flash_attn_install_error.log"; \
              cp "${flash_attn_log}" "${flash_attn_error_detail_path}"; \
              flash_attn_error_detail_summary="$( { echo "flash-attn verbose log too long (${flash_attn_log_size} bytes); saved to ${flash_attn_error_detail_path}"; echo "----- log head -----"; head -n 120 "${flash_attn_log}"; echo "----- log tail -----"; tail -n 120 "${flash_attn_log}"; } )"; \
            fi; \
            echo "[Qwen3-TTS][build] flash-attn install failed: ${flash_attn_error}" >&2; \
            if [ "${REQUIRE_FLASH_ATTN:-0}" = "1" ]; then \
              echo "[ERROR] flash-attn installation failed and REQUIRE_FLASH_ATTN=1" >&2; \
              FLASH_ATTN_ERROR_DETAIL_SUMMARY="${flash_attn_error_detail_summary}" FLASH_ATTN_ERROR_DETAIL_PATH="${flash_attn_error_detail_path}" python -c 'import json, os, time; status_file="/app/qwen3_tts_install_status.json"; detail_summary=os.getenv("FLASH_ATTN_ERROR_DETAIL_SUMMARY", ""); detail_path=os.getenv("FLASH_ATTN_ERROR_DETAIL_PATH", ""); payload={"ok": False, "source": "docker-install", "error": "flash-attn installation failed and REQUIRE_FLASH_ATTN=1", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "flash_attn_error_detail_summary": detail_summary, "flash_attn_error_detail_path": detail_path}; open(status_file, "w", encoding="utf-8").write(json.dumps(payload, ensure_ascii=False) + "\n")'; \
              exit 1; \
            fi; \
            echo "[Qwen3-TTS][build] warning: flash-attn install failed; continuing with non-flash attention backend" >&2; \
          else \
            echo "[Qwen3-TTS][build] flash-attn install succeeded via ${flash_attn_source}"; \
          fi; \
        elif [ "${INSTALL_FLASH_ATTN:-1}" != "1" ]; then \
          flash_attn_error="flash-attn install skipped (INSTALL_FLASH_ATTN!=1)"; \
          echo "[Qwen3-TTS][build] flash-attn install skipped: INSTALL_FLASH_ATTN!=1"; \
        else \
          flash_attn_error="flash-attn install skipped (no cuda environment)"; \
          echo "[Qwen3-TTS][build] flash-attn install skipped: no cuda environment"; \
        fi; \
        echo "[Qwen3-TTS][build] flash-attn install attempted: ${flash_attn_attempted}"; \
        if python -c "import flash_attn" >/dev/null 2>&1; then \
          flash_attn_available=true; \
        fi; \
        SOX_AVAILABLE="${sox_available}" FLASH_ATTN_ATTEMPTED="${flash_attn_attempted}" FLASH_ATTN_AVAILABLE="${flash_attn_available}" FLASH_ATTN_ERROR="${flash_attn_error}" FLASH_ATTN_ERROR_DETAIL="${flash_attn_error_detail}" FLASH_ATTN_ERROR_DETAIL_SUMMARY="${flash_attn_error_detail_summary}" FLASH_ATTN_ERROR_DETAIL_PATH="${flash_attn_error_detail_path}" python -c 'import json, os, time; status_file="/app/qwen3_tts_install_status.json"; payload={"ok": True, "source": "docker-install", "error": "", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "sox_available": os.getenv("SOX_AVAILABLE", "false") == "true", "flash_attn_attempted": os.getenv("FLASH_ATTN_ATTEMPTED", "false") == "true", "flash_attn_available": os.getenv("FLASH_ATTN_AVAILABLE", "false") == "true", "flash_attn_error": os.getenv("FLASH_ATTN_ERROR", ""), "flash_attn_error_detail": os.getenv("FLASH_ATTN_ERROR_DETAIL", ""), "flash_attn_error_detail_summary": os.getenv("FLASH_ATTN_ERROR_DETAIL_SUMMARY", ""), "flash_attn_error_detail_path": os.getenv("FLASH_ATTN_ERROR_DETAIL_PATH", "")}; open(status_file, "w", encoding="utf-8").write(json.dumps(payload, ensure_ascii=False) + "\n")'; \
      else \
        err="qwen-tts dependency installation failed; import failures: $(cat /tmp/qwen_tts_failed_imports.txt)"; \
        printf '{"ok":false,"source":"docker-install","error":"%s","timestamp":"%s"}\n' "${err}" "$(date -u +%FT%TZ)" > "${status_file}"; \
        echo "[ERROR] ${err}" >&2; \
        exit 1; \
      fi; \
    fi

# Re-pin core framework versions in case optional deps caused downgrades
RUN python -m pip install --no-cache-dir --upgrade "pydantic>=2.6" "fastapi>=0.110"

########################################
# Build stage: Style-Bert-VITS2 (isolated venv/layer)
########################################
FROM tts_build AS style_bert_vits2_build

ARG STYLE_BERT_VITS2_REPO_URL="https://github.com/litagin02/Style-Bert-VITS2.git"
ARG STYLE_BERT_VITS2_REF="master"

RUN apt-get update -o Acquire::Retries=3 \
    && apt-get install -y --no-install-recommends \
        git \
    && rm -rf /var/lib/apt/lists/*

RUN rm -rf /app/Style-Bert-VITS2 \
    && git clone --depth 1 --branch "${STYLE_BERT_VITS2_REF}" "${STYLE_BERT_VITS2_REPO_URL}" /app/Style-Bert-VITS2

# Keep Style-Bert-VITS2 dependencies isolated from existing Qwen3-TTS pins by using a dedicated venv.
RUN set -eux; \
    cd /app/Style-Bert-VITS2; \
    python3.11 -m venv /app/Style-Bert-VITS2/.venv; \
    site_packages="$("/app/Style-Bert-VITS2/.venv/bin/python" -c 'import site; print(site.getsitepackages()[0])')"; \
    printf '%s\n' \
      '/opt/venv/lib/python3.11/site-packages' \
      '/opt/venv/local/lib/python3.11/dist-packages' \
      '/opt/venv/lib/python3/dist-packages' \
      '/opt/venv/lib/python3.11/dist-packages' \
      > "${site_packages}/_runpod_opt_venv.pth"; \
    /app/Style-Bert-VITS2/.venv/bin/python -m pip install --no-cache-dir --upgrade pip wheel "setuptools<82"; \
    /app/Style-Bert-VITS2/.venv/bin/python -c "import torch, torchaudio, av; print(torch.__version__, torchaudio.__version__, av.__version__)"; \
    /app/Style-Bert-VITS2/.venv/bin/python -m pip install --no-cache-dir -e . --no-deps; \
    /app/Style-Bert-VITS2/.venv/bin/python -m pip install --no-cache-dir \
      "numpy<2" \
      pyworld-prebuilt \
      loguru \
      pyopenjtalk-dict \
      transformers \
      cmudict \
      cn2an \
      g2p_en \
      GPUtil \
      "gradio>=4.32" \
      jieba \
      "nltk<=3.8.1" \
      num2words \
      pypinyin; \
    /app/Style-Bert-VITS2/.venv/bin/python -c "import pyopenjtalk; pyopenjtalk.g2p('辞書ウォームアップ')"

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
    SANDBOX_MODE=process \
    LLAMA_SERVER_PATH=/app/llama/bin/llama-server \
    LD_LIBRARY_PATH=/app/llama/lib:/usr/local/lib:${LD_LIBRARY_PATH} \
    NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility \
    INSTALL_FLASH_ATTN=1 \
    REQUIRE_FLASH_ATTN=0 \
    FLASH_ATTN_MAX_JOBS=""

WORKDIR /app

RUN apt-get update -o Acquire::Retries=3 \
    && apt-get install -y --no-install-recommends \
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
        software-properties-common \
        gnupg \
        sox \
        libsox-fmt-all \
    && update-ca-certificates \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        python3.11 \
        python3.11-venv \
        python3.11-distutils \
    && rm -rf /var/lib/apt/lists/*

RUN python3.11 -m venv /opt/venv
ENV PATH=/opt/venv/bin:${PATH}

# Copy application source and prebuilt venv artifacts from build stage.
COPY . /app
COPY --from=tts_build /opt/venv /opt/venv
COPY --from=tts_build /app/qwen3_tts_install_status.json /app/qwen3_tts_install_status.json
COPY --from=style_bert_vits2_build /app/Style-Bert-VITS2 /app/Style-Bert-VITS2

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

COPY docker/start-services.sh /usr/local/bin/start-services.sh
RUN chmod +x /usr/local/bin/start-services.sh

EXPOSE 8000 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=5 \
  CMD curl -fsS http://127.0.0.1:${CODEAGENT_PORT}/health >/dev/null || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/usr/local/bin/start-services.sh"]
