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

estimate_compile_units() {
    # Approximate total compilation units for progress estimation.
    find "$NGSPICE_SRC_DIR" -type f \( -name "*.c" -o -name "*.cc" -o -name "*.cpp" \) \
        | wc -l | tr -d '[:space:]'
}

run_build_with_progress() {
    local jobs="$1"
    local log_file="$2"
    local build_pid
    local start_ts now_ts elapsed compiled percent filled empty mins secs
    local bar_width=34
    local spinner='|/-\'
    local spin_idx=0
    local bar_done bar_todo
    local total_units

    total_units="$(estimate_compile_units)"
    if ! [[ "$total_units" =~ ^[0-9]+$ ]]; then
        total_units=0
    fi

    : > "$log_file"
    make -C "$NGSPICE_SRC_DIR" -j"$jobs" >"$log_file" 2>&1 &
    build_pid=$!
    start_ts="$(date +%s)"

    mins=0
    secs=0

    while kill -0 "$build_pid" 2>/dev/null; do
        now_ts="$(date +%s)"
        elapsed=$((now_ts - start_ts))
        mins=$((elapsed / 60))
        secs=$((elapsed % 60))

        percent=0
        if [ "$total_units" -gt 0 ]; then
            compiled="$(grep -Ec -- '(^|[[:space:]])-c([[:space:]]|$)' "$log_file" 2>/dev/null || true)"
            if ! [[ "$compiled" =~ ^[0-9]+$ ]]; then
                compiled=0
            fi
            percent=$((compiled * 100 / total_units))
            if [ "$percent" -gt 99 ]; then
                percent=99
            fi
        fi

        filled=$((percent * bar_width / 100))
        empty=$((bar_width - filled))
        bar_done="$(printf '%*s' "$filled" '' | tr ' ' '#')"
        bar_todo="$(printf '%*s' "$empty" '')"

        printf "\rBuilding ngspice [%s%s] %3d%% %s %02d:%02d" \
            "$bar_done" "$bar_todo" "$percent" "${spinner:spin_idx:1}" "$mins" "$secs"
        spin_idx=$(((spin_idx + 1) % 4))
        sleep 1
    done

    set +e
    wait "$build_pid"
    local build_status=$?
    set -e

    if [ "$build_status" -ne 0 ]; then
        echo ""
        echo "ERROR: ngspice build failed. Last 40 lines from $log_file:"
        tail -n 40 "$log_file" || true
        exit "$build_status"
    fi

    printf "\rBuilding ngspice [%s] 100%% done %02d:%02d\n" \
        "$(printf '%*s' "$bar_width" '' | tr ' ' '#')" "$mins" "$secs"
}

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
        2>&1 | tee "$NGSPICE_BUILD_DIR/configure.log"
)

MAKE_JOBS="$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)"
echo "--- Building (jobs: $MAKE_JOBS) ---"
echo "    log: $NGSPICE_BUILD_DIR/build.log"
run_build_with_progress "$MAKE_JOBS" "$NGSPICE_BUILD_DIR/build.log"

echo "--- Installing ---"
make -C "$NGSPICE_SRC_DIR" install \
    2>&1 | tee "$NGSPICE_BUILD_DIR/install.log"

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
