#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_PYTHON="${PROJECT_ROOT}/.venv/bin/python"
OUTPUT_DIR="${PROJECT_ROOT}/build/nuitka"
APPDIR="${OUTPUT_DIR}/YAYMP.AppDir"
APP_LIB_DIR="${APPDIR}/usr/lib"
MPV_LIBRARY="${YAYMP_MPV_LIBRARY:-}"
MPV_LIBRARY_NAME=""

cd "${PROJECT_ROOT}"

if [[ "$(uname -s)" != "Linux" ]]; then
    echo "This script builds the Linux Nuitka standalone/AppDir only."
    exit 1
fi

if [[ ! -x "${VENV_PYTHON}" ]]; then
    echo "Missing virtualenv interpreter: ${VENV_PYTHON}"
    echo "Create it first:"
    echo "  python3 -m venv .venv"
    echo "  .venv/bin/python -m pip install -e '.[dev,packaging]'"
    exit 1
fi

if [[ -z "${MPV_LIBRARY}" ]]; then
    MPV_LIBRARY="$(ldconfig -p | awk '/libmpv\.so\.(2|1) / { print $NF; exit }')"
fi

if [[ -z "${MPV_LIBRARY}" || ! -f "${MPV_LIBRARY}" ]]; then
    echo "Missing libmpv shared library. Install libmpv1/libmpv2 or set YAYMP_MPV_LIBRARY."
    exit 1
fi

MPV_LIBRARY_NAME="$(basename "${MPV_LIBRARY}")"

mkdir -p "${OUTPUT_DIR}"
rm -rf \
    "${OUTPUT_DIR}/nuitka_entry.build" \
    "${OUTPUT_DIR}/nuitka_entry.dist" \
    "${OUTPUT_DIR}/nuitka_entry.onefile-build" \
    "${APPDIR}"

"${VENV_PYTHON}" -m nuitka \
    --standalone \
    --plugin-enable=pyside6 \
    --include-package=app \
    --include-package-data=app.presentation.qt \
    --include-data-files="${MPV_LIBRARY}=lib/${MPV_LIBRARY_NAME}" \
    --output-dir="${OUTPUT_DIR}" \
    --output-filename=yaymp \
    tools/nuitka_entry.py

mkdir -p "${APPDIR}/usr/bin" "${APPDIR}/usr/lib" "${APPDIR}/usr/share/applications"
cp -a "${OUTPUT_DIR}/nuitka_entry.dist/." "${APPDIR}/usr/bin/"
cp -f "${MPV_LIBRARY}" "${APP_LIB_DIR}/${MPV_LIBRARY_NAME}"
chmod u+rw "${APP_LIB_DIR}/${MPV_LIBRARY_NAME}"
"${VENV_PYTHON}" tools/bundle_linux_libs.py \
    --root-library "${APP_LIB_DIR}/${MPV_LIBRARY_NAME}" \
    --target-dir "${APP_LIB_DIR}"

cat >"${APPDIR}/AppRun" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
APPDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export LD_LIBRARY_PATH="${APPDIR}/usr/lib:${APPDIR}/usr/bin/lib:${LD_LIBRARY_PATH:-}"
exec "${APPDIR}/usr/bin/yaymp" "$@"
EOF
chmod +x "${APPDIR}/AppRun"

cat >"${APPDIR}/yaymp.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=YAYMP
Exec=yaymp
Categories=Audio;Music;Player;
Terminal=false
EOF
cp "${APPDIR}/yaymp.desktop" "${APPDIR}/usr/share/applications/yaymp.desktop"

echo "Built: ${OUTPUT_DIR}/nuitka_entry.dist"
echo "Built AppDir: ${APPDIR}"
