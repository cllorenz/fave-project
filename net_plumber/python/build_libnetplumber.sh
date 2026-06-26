#!/usr/bin/env bash
#
# Build the libnetplumber pybind11 module (FaVe P1, see APKEEP_BACKEND.md).
#
# Compiles net_plumber/python/libnetplumber.cpp and links it against
# NetPlumber's prebuilt core objects (everything under build/src except the
# main() entrypoint and the CppUnit test objects) plus log4cxx, producing an
# importable extension module next to this script.
#
# Prerequisites: NetPlumber already built (`make -C net_plumber/build all`),
# plus python3-dev, pybind11 headers (pybind11-dev), liblog4cxx-dev.
#
# The -D defines MUST match the canonical build (sources.mk USER_FLAGS) for ABI
# compatibility with the prebuilt objects.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NP="$(cd "$HERE/.." && pwd)"
SRC="$NP/src"
BUILD="$NP/build"

# Must match the canonical build (sources.mk USER_FLAGS) for ABI compatibility,
# plus JSON_IS_AMALGAMATION (the vendored jsoncpp is amalgamated -- no config.h).
USER_FLAGS=(-DWITH_EXTRA_NEW -DCHECK_ANOMALIES -DSTRICT_RW -DJSON_IS_AMALGAMATION)

# The prebuilt objects must be position-independent to go into a shared object.
# The makefile builds a plain executable (no -fPIC), so ensure a -fPIC build via
# the DEBUG_FLAGS hook (the same hook the sanitizer CI job uses). A clean is
# required because make won't rebuild up-to-date-but-non-PIC objects. PIC
# executables work identically, so this does not affect the net_plumber binary.
# Set LIBNP_ASSUME_PIC=1 to skip (when the caller already did a -fPIC build).
if [ "${LIBNP_ASSUME_PIC:-0}" != "1" ]; then
    echo "libnetplumber: (re)building NetPlumber core with -fPIC"
    make -s -C "$BUILD" clean
    make -s -j -C "$BUILD" DEBUG_FLAGS=-fPIC all
fi

# Core objects to link: all built objects except main.o (CLI/RPC entrypoint)
# and the CppUnit test objects.
mapfile -t OBJS < <(find "$BUILD/src" -name '*.o' ! -path '*/test/*' ! -name 'main.o' | sort)
if [ "${#OBJS[@]}" -eq 0 ]; then
    echo "libnetplumber: no NetPlumber objects found under $BUILD/src -- run 'make -C $BUILD all' first" >&2
    exit 1
fi

# pybind11 include: prefer the python module, fall back to the system headers
# (pybind11-dev installs /usr/include/pybind11).
PYBIND_INC="$(python3 -c 'import pybind11; print("-I"+pybind11.get_include())' 2>/dev/null || true)"
if [ -z "$PYBIND_INC" ] && [ -d /usr/include/pybind11 ]; then
    PYBIND_INC="-I/usr/include"
fi
[ -n "$PYBIND_INC" ] || { echo "libnetplumber: pybind11 headers not found (install pybind11-dev)" >&2; exit 1; }

EXT_SUFFIX="$(python3-config --extension-suffix)"
OUT="$HERE/libnetplumber${EXT_SUFFIX}"

echo "libnetplumber: compiling -> $OUT"
# shellcheck disable=SC2046
g++ -O3 -fPIC -shared -fvisibility=hidden -std=c++17 \
    "${USER_FLAGS[@]}" \
    $(python3-config --includes) $PYBIND_INC \
    -I"$SRC/net_plumber" -I"$SRC/headerspace" -I"$SRC/jsoncpp" \
    "$HERE/libnetplumber.cpp" "${OBJS[@]}" \
    -llog4cxx \
    -o "$OUT"

echo "libnetplumber: built $OUT"
