#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_PYTHON="${PROJECT_ROOT}/.venv/bin/python"

cd "${PROJECT_ROOT}"

if [[ ! -x "${VENV_PYTHON}" ]]; then
    echo "Missing virtualenv interpreter: ${VENV_PYTHON}"
    echo "Create it first:"
    echo "  python3 -m venv .venv"
    echo "  .venv/bin/python -m pip install -e '.[dev]'"
    read -r -p "Press Enter to close..."
    exit 1
fi

export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-offscreen}"
export PYTHONPATH="${PROJECT_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"

"${VENV_PYTHON}" -m pytest

read -r -p "Tests finished. Press Enter to close..."
