#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_PYTHON="${PROJECT_ROOT}/.venv/bin/python"
OUTPUT_DIR="${PROJECT_ROOT}/build/nuitka"
VENDOR_DIR="${OUTPUT_DIR}/vendor"
VENDORED_MPV_LIBRARY="${VENDOR_DIR}/libmpv.2.dylib"
APP_DIR="${OUTPUT_DIR}/nuitka_entry.app"
APP_LIB_DIR="${APP_DIR}/Contents/MacOS/lib"
MPV_LIBRARY="${YAYMP_MPV_LIBRARY:-/opt/homebrew/lib/libmpv.2.dylib}"

cd "${PROJECT_ROOT}"

if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "This script builds the macOS Nuitka standalone/app bundle only."
    exit 1
fi

if [[ ! -x "${VENV_PYTHON}" ]]; then
    echo "Missing virtualenv interpreter: ${VENV_PYTHON}"
    echo "Create it first:"
    echo "  python3 -m venv .venv"
    echo "  .venv/bin/python -m pip install -e '.[dev,packaging]'"
    exit 1
fi

if [[ ! -f "${MPV_LIBRARY}" ]]; then
    echo "Missing libmpv dylib: ${MPV_LIBRARY}"
    echo "Install mpv with Homebrew or set YAYMP_MPV_LIBRARY."
    exit 1
fi

MPV_LIBRARY="$(realpath "${MPV_LIBRARY}")"

mkdir -p "${OUTPUT_DIR}"
rm -rf \
    "${OUTPUT_DIR}/nuitka_entry.app" \
    "${OUTPUT_DIR}/nuitka_entry.build" \
    "${OUTPUT_DIR}/nuitka_entry.dist" \
    "${OUTPUT_DIR}/nuitka_entry.onefile-build"
mkdir -p "${VENDOR_DIR}"
cp -f "${MPV_LIBRARY}" "${VENDORED_MPV_LIBRARY}"
chmod u+rw "${VENDORED_MPV_LIBRARY}"
xattr -c "${VENDORED_MPV_LIBRARY}" 2>/dev/null || true

"${VENV_PYTHON}" -m nuitka \
    --standalone \
    --macos-create-app-bundle \
    --macos-app-name=YAYMP \
    --macos-app-icon=none \
    --plugin-enable=pyside6 \
    --include-package=app \
    --include-package-data=app.presentation.qt \
    --include-data-files="${VENDORED_MPV_LIBRARY}=lib/libmpv.2.dylib" \
    --output-dir="${OUTPUT_DIR}" \
    --output-filename=yaymp \
    tools/nuitka_entry.py

"${VENV_PYTHON}" tools/bundle_macos_dylibs.py \
    --root-library "${VENDORED_MPV_LIBRARY}" \
    --target-dir "${APP_LIB_DIR}"

codesign --force --deep --sign - "${APP_DIR}"

echo "Built: ${APP_DIR}"
