#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

NGSPICE_VERSION="${NGSPICE_VERSION:-45.2}"
NGSPICE_ROOT="$PROJECT_DIR/third_party/ngspice"
NGSPICE_SRC_ROOT="$NGSPICE_ROOT/src"
NGSPICE_BUILD_ROOT="$NGSPICE_ROOT/build"
NGSPICE_INSTALL_ROOT="$NGSPICE_ROOT/install"
NGSPICE_TARBALL="$NGSPICE_ROOT/ngspice-${NGSPICE_VERSION}.tar.gz"
NGSPICE_SRC_DIR="$NGSPICE_SRC_ROOT/ngspice-${NGSPICE_VERSION}"
NGSPICE_BUILD_DIR="$NGSPICE_BUILD_ROOT/ngspice-${NGSPICE_VERSION}"
NGSPICE_BIN="$NGSPICE_INSTALL_ROOT/bin/ngspice"

NGSPICE_URL="https://sourceforge.net/projects/ngspice/files/ng-spice-rework/${NGSPICE_VERSION}/ngspice-${NGSPICE_VERSION}.tar.gz/download"

echo "=== Local ngspice install ==="
echo "Version:  $NGSPICE_VERSION"
echo "Prefix:   $NGSPICE_INSTALL_ROOT"
echo ""

if [ -x "$NGSPICE_BIN" ]; then
    echo "ngspice already installed at $NGSPICE_BIN"
    "$NGSPICE_BIN" --version | head -n 2 || true
    exit 0
fi

if [ -d "$NGSPICE_INSTALL_ROOT" ]; then
    rm -rf "$NGSPICE_INSTALL_ROOT"
fi

for tool in curl tar make gcc; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        echo "ERROR: required build tool '$tool' not found in PATH."
        exit 1
    fi
done

mkdir -p "$NGSPICE_ROOT" "$NGSPICE_SRC_ROOT" "$NGSPICE_BUILD_ROOT"

if [ ! -f "$NGSPICE_TARBALL" ]; then
    echo "--- Downloading ngspice source tarball ---"
    curl -L --fail --retry 3 --retry-delay 2 \
        -o "$NGSPICE_TARBALL" \
        "$NGSPICE_URL"
else
    echo "--- Reusing existing tarball ---"
fi

if [ ! -d "$NGSPICE_SRC_DIR" ]; then
    echo "--- Extracting source ---"
    tar -xzf "$NGSPICE_TARBALL" -C "$NGSPICE_SRC_ROOT"
fi

# SourceForge tarballs can contain maintainer inputs (configure.ac, *.am)
# newer than generated outputs (configure, aclocal.m4, Makefile.in), which
# makes `make` try to run modern autotools unavailable on shared lab hosts.
if [ -f "$NGSPICE_SRC_DIR/configure" ] && [ -f "$NGSPICE_SRC_DIR/configure.ac" ]; then
    touch "$NGSPICE_SRC_DIR/configure"
fi
if [ -f "$NGSPICE_SRC_DIR/aclocal.m4" ]; then
    touch "$NGSPICE_SRC_DIR/aclocal.m4"
fi
if [ -f "$NGSPICE_SRC_DIR/src/include/ngspice/config.h.in" ]; then
    touch "$NGSPICE_SRC_DIR/src/include/ngspice/config.h.in"
fi
find "$NGSPICE_SRC_DIR" -name "Makefile.in" -exec touch {} +

mkdir -p "$NGSPICE_BUILD_DIR"

echo "--- Configuring ---"
(
    cd "$NGSPICE_SRC_DIR"
    ./configure \
        --prefix="$NGSPICE_INSTALL_ROOT" \
        --disable-debug \
        --without-x \
        --enable-xspice \
        --enable-cider \
        --disable-maintainer-mode \
        --disable-dependency-tracking \
        > "$NGSPICE_BUILD_DIR/configure.log" 2>&1
)

echo "--- Building ---"
make -C "$NGSPICE_SRC_DIR" -j"$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)" \
    > "$NGSPICE_BUILD_DIR/build.log" 2>&1

echo "--- Installing ---"
make -C "$NGSPICE_SRC_DIR" install \
    > "$NGSPICE_BUILD_DIR/install.log" 2>&1

if [ ! -x "$NGSPICE_BIN" ]; then
    echo "ERROR: install completed but ngspice binary not found at $NGSPICE_BIN"
    exit 1
fi

echo "--- Installed ngspice ---"
"$NGSPICE_BIN" --version | head -n 3 || true
echo ""
echo "Environment hints:"
echo "  export EE201A_NGSPICE_BIN=\"$NGSPICE_BIN\""
echo "  export PATH=\"$NGSPICE_INSTALL_ROOT/bin:\$PATH\""
if [ -f "$NGSPICE_INSTALL_ROOT/lib/libngspice.so" ]; then
    echo "  export NGSPICE_LIBRARY_PATH=\"$NGSPICE_INSTALL_ROOT/lib/libngspice.so\""
    echo "  export LD_LIBRARY_PATH=\"$NGSPICE_INSTALL_ROOT/lib:\$LD_LIBRARY_PATH\""
fi
