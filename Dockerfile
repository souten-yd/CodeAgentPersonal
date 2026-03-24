# syntax=docker/dockerfile:1.7

########################################
# Builder stage: compile llama.cpp with CUDA
########################################
ARG CUDA_VERSION=12.8.0
ARG UBUNTU_VERSION=22.04
ARG LLAMA_CPP_REF=b8480

FROM nvidia/cuda:${CUDA_VERSION}-cudnn-devel-ubuntu${UBUNTU_VERSION} AS builder

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
        ninja-build \
        git \
        ca-certificates \
        curl \
        libcurl4-openssl-dev \
        libssl-dev \
        pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
RUN git clone --depth 1 --branch ${LLAMA_CPP_REF} https://github.com/ggml-org/llama.cpp.git
WORKDIR /src/llama.cpp

# Avoid host-specific tuning in cloud containers.
# Build dynamic backend libraries so runtime linkage is more robust.
ARG CUDA_DOCKER_ARCH=default
RUN if [ "${CUDA_DOCKER_ARCH}" != "default" ]; then \
        export CMAKE_CUDA_ARCH="-DCMAKE_CUDA_ARCHITECTURES=${CUDA_DOCKER_ARCH}"; \
    fi \
    && cmake -S . -B build -G Ninja \
        -DCMAKE_BUILD_TYPE=Release \
        -DGGML_CUDA=ON \
        -DGGML_NATIVE=OFF \
        -DGGML_BACKEND_DL=ON \
        -DLLAMA_CURL=ON \
        -DLLAMA_BUILD_TESTS=OFF \
        ${CMAKE_CUDA_ARCH:-} \
    && cmake --build build --config Release -j"$(nproc)"

RUN mkdir -p /out/bin /out/lib \
    && cp -v build/bin/llama-server /out/bin/ \
    && cp -v build/bin/llama-cli /out/bin/ \
    && find build -maxdepth 3 -type f \( -name '*.so' -o -name '*.so.*' \) -exec cp -Pv {} /out/lib/ \;

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

RUN apt-get update \
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
COPY --from=builder /out/bin/llama-server /app/llama/bin/llama-server
COPY --from=builder /out/bin/llama-cli /app/llama/bin/llama-cli
COPY --from=builder /out/lib/ /app/llama/lib/

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
