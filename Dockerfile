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
        python3 \
        tar \
    && rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    ASSET_REGEX='^llama\.cpp-b[0-9]+-cuda-12\.8\.tar\.gz$'; \
    RELEASE_JSON="$(curl -fsSL https://api.github.com/repos/ai-dock/llama.cpp-cuda/releases/latest)"; \
    SELECTED="$(python3 -c 'import json,re,sys; release=json.loads(sys.argv[1]); pattern=re.compile(sys.argv[2]); asset=next((a for a in release.get(\"assets\",[]) if pattern.match(a.get(\"name\",\"\"))),None); sys.exit(1) if asset is None else None; print(asset.get(\"browser_download_url\",\"\")); print(asset.get(\"name\",\"\"))' "${RELEASE_JSON}" "${ASSET_REGEX}")"; \
    ASSET_URL="$(echo "${SELECTED}" | sed -n '1p')"; \
    ASSET_NAME="$(echo "${SELECTED}" | sed -n '2p')"; \
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
    LD_LIBRARY_PATH=/app/llama/lib:/usr/local/lib:${LD_LIBRARY_PATH}

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
        python -m pip install fastapi 'uvicorn[standard]' pydantic requests; \
    fi

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
