#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_RUFF="${PROJECT_ROOT}/.venv/bin/ruff"

cd "${PROJECT_ROOT}"

if [[ ! -x "${VENV_RUFF}" ]]; then
    echo "Missing virtualenv ruff executable: ${VENV_RUFF}"
    echo "Create it first:"
    echo "  python3 -m venv .venv"
    echo "  .venv/bin/python -m pip install -e '.[dev]'"
    read -r -p "Press Enter to close..."
    exit 1
fi

export PYTHONPATH="${PROJECT_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"

"${VENV_RUFF}" check src tests
