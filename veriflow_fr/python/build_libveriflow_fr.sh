#!/usr/bin/env bash
# Build the libveriflow_fr pybind11 module (VERIFLOW_PLAN.md D3). The engine is
# compiled with the same compiler and -O3 as NetPlumber (D3, condition 2).

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$(cd "$HERE/../src" && pwd)"

# pybind11: prefer the python module, fall back to the system headers
# (pybind11-dev), exactly as net_plumber/python/build_libnetplumber.sh does.
PYTHON="${PYTHON:-python3}"
PYBIND_INC="$("$PYTHON" -c 'import pybind11; print("-I"+pybind11.get_include())' 2>/dev/null || true)"
if [ -z "$PYBIND_INC" ] && [ -d /usr/include/pybind11 ]; then
    PYBIND_INC="-I/usr/include"
fi
[ -n "$PYBIND_INC" ] || { echo "libveriflow_fr: pybind11 headers not found (install pybind11-dev)" >&2; exit 1; }

OUT="$HERE/libveriflow_fr$(python3-config --extension-suffix)"
echo "libveriflow_fr: compiling -> $OUT"
# shellcheck disable=SC2046
g++ -O3 -fPIC -shared -fvisibility=hidden -std=c++17 -Wall -Wextra \
    $(python3-config --includes) $PYBIND_INC \
    "$HERE/libveriflow_fr.cpp" "$SRC/veriflow.cc" "$SRC/queries.cc" \
    -o "$OUT"
echo "libveriflow_fr: built $OUT"
