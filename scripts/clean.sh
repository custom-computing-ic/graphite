#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Limit package artifacts to the project root; skip environments and Git data
# when looking for Python caches throughout the source tree.
find "${ROOT_DIR}" -mindepth 1 -maxdepth 1 -type d \
  \( -name dist -o -name build -o -name '*.egg-info' \) \
  -exec rm -rf -- {} +
find "${ROOT_DIR}" -type d \
  \( -name .git -o -name .venv -o -name venv -o -name .tox -o -name .nox \) -prune -o \
  \( -name __pycache__ -o -name .pytest_cache -o -name .mypy_cache -o -name .ruff_cache \) \
  -prune -exec rm -rf -- {} +
