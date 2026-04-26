#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

export NEXUS_SEARXNG_URL="${NEXUS_SEARXNG_URL:-http://127.0.0.1:8088}"

exec bash scripts/runpod_start.sh "$@"
