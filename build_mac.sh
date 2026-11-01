#!/usr/bin/env bash
# exDesktop macOS Native Build & Validation Script with Compiler Cache
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ -n "${TDESKTOP_API_ID:-}" ]; then
    API_ARGS=(-DTDESKTOP_API_ID="${TDESKTOP_API_ID}" -DTDESKTOP_API_HASH="${TDESKTOP_API_HASH}")
else
    API_ARGS=(-DTDESKTOP_API_TEST=ON)
fi

MODE="${1:-configure}"

# Ensure cache directory & size defaults for .o object files
export SCCACHE_DIR="${SCCACHE_DIR:-$HOME/.cache/sccache}"
export SCCACHE_CACHE_SIZE="${SCCACHE_CACHE_SIZE:-15G}"
export CCACHE_DIR="${CCACHE_DIR:-$HOME/.cache/ccache}"
export CCACHE_MAXSIZE="${CCACHE_MAXSIZE:-15G}"

show_help() {
    cat <<EOF
exDesktop macOS Native Builder with Compiler Cache

Usage:
  ./build_mac.sh [command] [options]

Commands:
  configure           Configure CMake for macOS with compiler caching
  build               Build Telegram binary / app bundle
  help                Show this message

Environment Variables:
  TDESKTOP_API_ID     Telegram API ID (default: test credentials)
  TDESKTOP_API_HASH   Telegram API Hash
  BUILD_DIR           Build directory (default: out)
  CONFIG              Build configuration: Release or Debug (default: Release)
  ARCH                Target architecture: arm64 or x86_64 (default: host architecture)
EOF
}

run_configure() {
    local BUILD_DIR="${BUILD_DIR:-out}"
    local CONFIG="${CONFIG:-Release}"
    local ARCH="${ARCH:-$(uname -m)}"

    local CACHE_ARGS=()
    if command -v sccache >/dev/null 2>&1; then
        echo "==> Using sccache compiler cache for accelerated rebuilds."
        CACHE_ARGS=(-DDESKTOP_APP_USE_COMPILER_CACHE=ON)
    elif command -v ccache >/dev/null 2>&1; then
        echo "==> Using ccache compiler cache for accelerated rebuilds."
        CACHE_ARGS=(-DDESKTOP_APP_USE_COMPILER_CACHE=ON)
    else
        echo "==> Neither sccache nor ccache found. Rebuilds will not be cached."
        echo "==> Tip: Run 'brew install sccache' or 'brew install ccache' for 2x faster builds."
        CACHE_ARGS=(-DDESKTOP_APP_USE_COMPILER_CACHE=OFF)
    fi

    echo "==> Configuring CMake in ${BUILD_DIR} (${CONFIG}, ${ARCH})..."
    cmake -B "${BUILD_DIR}" -G Ninja \
        -DCMAKE_BUILD_TYPE="${CONFIG}" \
        -DCMAKE_OSX_ARCHITECTURES="${ARCH}" \
        "${API_ARGS[@]}" \
        "${CACHE_ARGS[@]}" \
        "${@:2}"
}

run_build() {
    local BUILD_DIR="${BUILD_DIR:-out}"
    local CONFIG="${CONFIG:-Release}"
    if [ ! -f "${BUILD_DIR}/build.ninja" ] && [ ! -f "${BUILD_DIR}/Makefile" ]; then
        run_configure "$@"
    fi
    echo "==> Compiling exDesktop macOS (${CONFIG})..."
    cmake --build "${BUILD_DIR}" --config "${CONFIG}" --target Telegram
    echo "==> Build complete: ${BUILD_DIR}/bin/Telegram.app"
}

case "${MODE}" in
    configure)
        run_configure "$@"
        ;;
    build)
        run_build "$@"
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo "Unknown command: ${MODE}"
        show_help
        exit 1
        ;;
esac
