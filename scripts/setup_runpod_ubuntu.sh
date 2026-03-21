#!/usr/bin/env bash
set -euo pipefail

CI_MODE=0
if [[ "${1:-}" == "--ci" ]]; then
  CI_MODE=1
fi

if ! command -v apt-get >/dev/null 2>&1; then
  echo "This script currently supports Ubuntu/Debian (apt-get) only." >&2
  exit 1
fi

SUDO=""
if [[ "$(id -u)" -ne 0 ]]; then
  SUDO="sudo"
fi

# NVIDIA + Vulkan + build essentials used by Python wheels and runtime checks.
${SUDO} apt-get update
${SUDO} DEBIAN_FRONTEND=noninteractive apt-get install -y \
  ca-certificates \
  curl \
  git \
  build-essential \
  python3.11 \
  python3.11-venv \
  python3-pip \
  vulkan-tools \
  libvulkan1 \
  mesa-vulkan-drivers

if command -v nvidia-smi >/dev/null 2>&1; then
  echo "NVIDIA driver is available:"
  nvidia-smi || true
else
  echo "nvidia-smi was not found. Install NVIDIA driver on the Runpod image first." >&2
fi

if [[ "${CI_MODE}" -eq 0 ]]; then
  cat <<'EOF'
Runpod host bootstrap completed.
Next steps:
1) Install and configure GitHub Actions self-hosted runner labels: self-hosted, linux, x64, nvidia, runpod
2) Verify `python3.11 --version` and `vulkaninfo --summary`
3) Start the runner service and trigger `.github/workflows/runpod-test.yml`
EOF
fi
